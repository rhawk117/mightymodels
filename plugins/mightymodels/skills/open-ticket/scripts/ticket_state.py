"""Write and validate a mightymodels ticket, and stage its work unit.

ticket.yml is written here in one canonical YAML subset and parsed back in exactly that
subset: two levels of mappings, scalars, and lists of scalars, with trailing comments. A
hand edit that stays in the subset validates; anything else is refused with its line
number rather than misread. Validation also refreshes the ticket section of
work-unit.json, leaving any progress another skill recorded there untouched. Both commands
keep .mightymodels/ in the repository's local exclude file, because nothing under it is
ever tracked.

Usage:
    python3 ticket_state.py write --slug SLUG  < answers.json
    python3 ticket_state.py validate --slug SLUG
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

type Node = dict[str, Node] | list[Node] | str | int | bool | None
type Scalar = str | int | bool | None

SCHEMA_VERSION = 1
EXIT_REJECTED = 2
INDENT = 2
CONTEXT_LIMIT = 6
DECODER = json.JSONDecoder()
EXCLUDE_LINE = '.mightymodels/'

DEFAULT_MODELS: dict[str, str | None] = {
    'primary-agent': None,
    'code-scout': 'gpt-5.6-luna',
    'web-scout': 'gpt-5.6-luna',
    'qualitylens': 'gpt-5.6-luna',
    'engineer': None,
    'architect': None,
    'gitty-up': 'gpt-5.6-luna',
    'wingman': 'gpt-5.6-sol',
    'merge-vader-reviewer': 'gpt-5.6-sol',
    'uncle-bob-reviewer': 'claude-sonnet-5',
}
TOP_LEVEL = frozenset(
    {
        'task',
        'summary',
        'triaged-at',
        'context',
        'companion-docs',
        'subagent-models',
        'handoff-context',
        'investigations',
    }
)
COMPANION_KEYS = frozenset({'issue-number', 'jira-key', 'reference-urls'})
HANDOFF_KEYS = frozenset({'scope', 'plan-first', 'branch-name', 'worktrees-okay'})


class Scope(StrEnum):
    SM = 'sm'
    MED = 'med'
    LARGE = 'large'


class Command(StrEnum):
    WRITE = 'write'
    VALIDATE = 'validate'


ENGINEER_MODEL: dict[Scope, str] = {
    Scope.SM: 'gpt-5.6-luna',
    Scope.MED: 'gpt-5.6-luna',
    Scope.LARGE: 'claude-sonnet-5',
}
ARCHITECT_MODEL: dict[Scope, str] = {
    Scope.SM: 'gpt-5.6-terra',
    Scope.MED: 'gpt-5.6-terra',
    Scope.LARGE: 'gpt-5.6-sol',
}


class TicketError(Exception):
    pass


class SubsetError(TicketError):
    def __init__(self, number: int, reason: str) -> None:
        super().__init__(f'ticket.yml:{number}: {reason}')


class TicketExistsError(TicketError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} exists; edit it by hand, then run validate')


class MissingTicketError(TicketError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} does not exist; run write first')


class InvalidAnswersError(TicketError):
    def __init__(self, cause: Exception) -> None:
        super().__init__(f'answers: missing or invalid field: {cause}')


class AnswersNotJsonError(TicketError):
    def __init__(self) -> None:
        super().__init__('answers: stdin is not a JSON object')


class InvalidTicketError(TicketError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__('ticket.yml is invalid:\n  ' + '\n  '.join(problems))


class NotAListError(TicketError):
    def __init__(self, key: str) -> None:
        super().__init__(f'answers: {key} must be a list')


class NoRepositoryError(TicketError):
    def __init__(self, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


@dataclass(frozen=True, slots=True)
class Line:
    number: int
    indent: int
    text: str


@dataclass(frozen=True, slots=True)
class Answers:
    summary: str
    scope: Scope
    compaction: bool
    branch: str
    context: tuple[str, ...]
    issue: int | None = None
    jira: str | None = None
    reference_urls: tuple[str, ...] = ()
    investigations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path
    slug: str

    @property
    def ticket_dir(self) -> Path:
        return self.root / '.mightymodels' / self.slug

    @property
    def ticket(self) -> Path:
        return self.ticket_dir / 'ticket.yml'

    @property
    def work_unit(self) -> Path:
        return self.ticket_dir / 'work-unit.json'

    def investigation(self, investigation: str) -> Path:
        runtime = self.root / '.mightymodels' / '.runtime' / 'investigations'
        return runtime / f'{investigation}.jsonl'


@dataclass(slots=True)
class Problems:
    items: list[str] = field(default_factory=list)

    def require(self, condition: bool, message: str) -> None:  # noqa: FBT001 - the condition is the check itself, not a mode switch
        if not condition:
            self.items.append(message)


def now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec='seconds')


def repository_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / '.git').exists():
            return candidate
    raise NoRepositoryError(start)


def read_text(path: Path) -> str | None:
    return path.read_text(encoding='utf-8').strip() if path.is_file() else None


def git_dir(root: Path) -> Path:
    dot_git = root / '.git'
    if dot_git.is_file():
        pointer = read_text(dot_git) or ''
        return (root / pointer.removeprefix('gitdir:').strip()).resolve()
    return dot_git


def common_dir(directory: Path) -> Path:
    pointer = read_text(directory / 'commondir')
    return (directory / pointer).resolve() if pointer else directory


def ensure_excluded(root: Path) -> None:
    exclude = common_dir(git_dir(root)) / 'info' / 'exclude'
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')


def quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def scalar_text(*, value: Scalar) -> str:
    match value:
        case None:
            return ''
        case bool():
            return 'true' if value else 'false'
        case int():
            return str(value)
        case _:
            return quoted(value)


def entry_line(key: str, depth: int, *, value: Scalar) -> str:
    rendered = scalar_text(value=value)
    pad = ' ' * (depth * INDENT)
    return f'{pad}{key}: {rendered}'.rstrip()


def list_lines(key: str, values: tuple[str, ...], depth: int) -> list[str]:
    pad = ' ' * (depth * INDENT)
    items = [f'{pad}{" " * INDENT}- {quoted(value)}' for value in values]
    return [f'{pad}{key}:', *items]


def ticket_text(slug: str, answers: Answers) -> str:
    models = {
        **DEFAULT_MODELS,
        'engineer': ENGINEER_MODEL[answers.scope],
        'architect': ARCHITECT_MODEL[answers.scope],
    }
    lines = [
        entry_line('task', 0, value=slug),
        entry_line('summary', 0, value=answers.summary),
        entry_line('triaged-at', 0, value=now()),
        *list_lines('context', answers.context, 0),
        'companion-docs:',
        entry_line('issue-number', 1, value=answers.issue),
        entry_line('jira-key', 1, value=answers.jira),
        *list_lines('reference-urls', answers.reference_urls, 1),
        'subagent-models:',
        *(entry_line(worker, 1, value=model) for worker, model in models.items()),
        'handoff-context:',
        entry_line('scope', 1, value=str(answers.scope)),
        entry_line('plan-first', 1, value=answers.compaction),
        entry_line('branch-name', 1, value=answers.branch),
        entry_line('worktrees-okay', 1, value=False),
        *list_lines('investigations', answers.investigations, 0),
    ]
    return '\n'.join(lines) + '\n'


def value_text(text: str) -> str:
    if text.startswith('"'):
        return text
    if text.startswith('#'):
        return ''
    return text.split(' #', 1)[0].rstrip()


def source_lines(source: str) -> list[Line]:
    lines: list[Line] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        content = raw.rstrip()
        if not content.strip() or content.lstrip().startswith('#'):
            continue
        indent = len(content) - len(content.lstrip(' '))
        if indent % INDENT or '\t' in content[:indent]:
            raise SubsetError(number, 'indentation must be a multiple of two spaces')
        lines.append(Line(number=number, indent=indent, text=content.strip()))
    return lines


def quoted_scalar(text: str, number: int) -> str:
    try:
        value, end = DECODER.raw_decode(text)
    except json.JSONDecodeError as error:
        raise SubsetError(number, 'unterminated quoted string') from error
    rest = text[end:].strip()
    if rest and not rest.startswith('#'):
        raise SubsetError(number, f'unexpected text after the string: {rest}')
    return str(value)


PLAIN_SCALARS: dict[str, bool | None] = {'true': True, 'false': False, '': None}


def scalar(text: str, number: int) -> Node:
    if text.startswith('"'):
        return quoted_scalar(text, number)
    if text in PLAIN_SCALARS:
        return PLAIN_SCALARS[text]
    if text.isdigit():
        return int(text)
    if text[0] in "'[{&*!|>":
        raise SubsetError(number, f'unsupported YAML syntax: {text}')
    return text


def split_key(line: Line) -> tuple[str, str]:
    key, separator, rest = line.text.partition(':')
    if not separator or not key or ' ' in key:
        raise SubsetError(line.number, f'expected "key: value", got {line.text}')
    return key, rest.strip()


@dataclass(slots=True)
class Parser:
    lines: list[Line]
    index: int = 0

    def peek_indent(self) -> int:
        return self.lines[self.index].indent if self.index < len(self.lines) else -1

    def block(self, indent: int) -> Node:
        if self.lines[self.index].text.startswith('- '):
            return self.sequence(indent)
        return self.mapping(indent)

    def sequence(self, indent: int) -> list[Node]:
        items: list[Node] = []
        while self.peek_indent() == indent:
            line = self.lines[self.index]
            if not line.text.startswith('- '):
                raise SubsetError(line.number, 'mixed list and mapping at one level')
            items.append(scalar(value_text(line.text[2:].strip()), line.number))
            self.index += 1
        return items

    def mapping(self, indent: int) -> dict[str, Node]:
        result: dict[str, Node] = {}
        while self.peek_indent() == indent:
            line = self.lines[self.index]
            key, rest = split_key(line)
            if key in result:
                raise SubsetError(line.number, f'duplicate key {key}')
            self.index += 1
            result[key] = self.value(rest, line)
        if self.peek_indent() > indent:
            raise SubsetError(self.lines[self.index].number, 'unexpected indentation')
        return result

    def value(self, rest: str, line: Line) -> Node:
        text = value_text(rest)
        if text:
            return scalar(text, line.number)
        child = self.peek_indent()
        return self.block(child) if child > line.indent else None


def parse(source: str) -> dict[str, Node]:
    parser = Parser(lines=source_lines(source))
    if not parser.lines:
        return {}
    tree = parser.block(0)
    if not isinstance(tree, dict):
        raise SubsetError(parser.lines[0].number, 'the top level must be a mapping')
    return tree


def as_mapping(node: Node) -> dict[str, Node]:
    return node if isinstance(node, dict) else {}


def check_top(tree: dict[str, Node], slug: str, problems: Problems) -> None:
    unknown = sorted(set(tree) - TOP_LEVEL)
    problems.require(not unknown, f'unknown top-level keys {unknown}; no consumer reads them')
    problems.require(tree.get('task') == slug, f'task must be {slug!r}')
    problems.require(bool(tree.get('summary')), 'summary is empty')
    context = tree.get('context')
    problems.require(
        isinstance(context, list) and 1 <= len(context) <= CONTEXT_LIMIT,
        f'context must be a list of 1 to {CONTEXT_LIMIT} lines',
    )


def check_models(models: dict[str, Node], problems: Problems) -> None:
    unknown = sorted(set(models) - set(DEFAULT_MODELS))
    problems.require(not unknown, f'subagent-models has unknown workers {unknown}')
    missing = sorted({'engineer', 'architect'} - {k for k, v in models.items() if v})
    problems.require(not missing, f'subagent-models needs a model for {missing}')


def check_handoff(handoff: dict[str, Node], problems: Problems) -> None:
    unknown = sorted(set(handoff) - HANDOFF_KEYS)
    problems.require(not unknown, f'handoff-context has unknown keys {unknown}')
    scopes = {scope.value for scope in Scope}
    problems.require(handoff.get('scope') in scopes, f'scope must be one of {sorted(scopes)}')
    problems.require(isinstance(handoff.get('plan-first'), bool), 'plan-first must be a bool')
    problems.require(bool(handoff.get('branch-name')), 'branch-name is empty')


def check_companions(companions: dict[str, Node], problems: Problems) -> None:
    unknown = sorted(set(companions) - COMPANION_KEYS)
    problems.require(not unknown, f'companion-docs has unknown keys {unknown}')
    issue = companions.get('issue-number')
    problems.require(issue is None or isinstance(issue, int), 'issue-number must be a number')


def check_investigations(tree: dict[str, Node], paths: Paths, problems: Problems) -> None:
    investigations = tree.get('investigations') or []
    problems.require(isinstance(investigations, list), 'investigations must be a list')
    for investigation in investigations if isinstance(investigations, list) else []:
        exists = paths.investigation(str(investigation)).is_file()
        problems.require(exists, f'investigation {investigation} has no ledger file')


def validate_tree(tree: dict[str, Node], paths: Paths) -> None:
    problems = Problems()
    check_top(tree, paths.slug, problems)
    check_models(as_mapping(tree.get('subagent-models')), problems)
    check_handoff(as_mapping(tree.get('handoff-context')), problems)
    check_companions(as_mapping(tree.get('companion-docs')), problems)
    check_investigations(tree, paths, problems)
    if problems.items:
        raise InvalidTicketError(problems.items)


def ticket_section(tree: dict[str, Node], paths: Paths) -> dict[str, Node]:
    handoff = as_mapping(tree.get('handoff-context'))
    companions = as_mapping(tree.get('companion-docs'))
    return {
        'ticket': str(paths.ticket.relative_to(paths.root)),
        'summary': tree.get('summary'),
        'branch': handoff.get('branch-name'),
        'scope': handoff.get('scope'),
        'plan_first': handoff.get('plan-first'),
        'models': as_mapping(tree.get('subagent-models')),
        'tracker': {
            'issue': companions.get('issue-number'),
            'jira': companions.get('jira-key'),
        },
        'validated_at': now(),
    }


def as_list(node: Node) -> list[Node]:
    return node if isinstance(node, list) else []


def read_work_unit(paths: Paths) -> dict[str, Node]:
    if not paths.work_unit.is_file():
        return {}
    return as_mapping(json.loads(paths.work_unit.read_text(encoding='utf-8')))


def linked_investigations(existing: dict[str, Node], tree: dict[str, Node]) -> list[Node]:
    previous = as_list(existing.get('investigations'))
    added = [item for item in as_list(tree.get('investigations')) if item not in previous]
    return [*previous, *added]


def atomic_write(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def strings(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw.get(key) or []
    if not isinstance(value, list):
        raise NotAListError(key)
    return tuple(str(item) for item in value)


def answers_from(raw: dict[str, object]) -> Answers:
    try:
        issue = raw.get('issue')
        return Answers(
            summary=str(raw['summary']),
            scope=Scope(raw['scope']),
            compaction=bool(raw['compaction']),
            branch=str(raw['branch']),
            context=strings(raw, 'context'),
            issue=None if issue is None else int(str(issue)),
            jira=None if raw.get('jira') is None else str(raw['jira']),
            reference_urls=strings(raw, 'reference_urls'),
            investigations=strings(raw, 'investigations'),
        )
    except (KeyError, ValueError) as error:
        raise InvalidAnswersError(error) from error


def run_write(options: argparse.Namespace, cwd: Path) -> str:
    paths = Paths(root=repository_root(cwd), slug=options.slug)
    if paths.ticket.exists():
        raise TicketExistsError(paths.ticket)
    try:
        answers = answers_from(json.loads(sys.stdin.read()))
    except json.JSONDecodeError as error:
        raise AnswersNotJsonError from error
    text = ticket_text(options.slug, answers)
    validate_tree(parse(text), paths)
    ensure_excluded(paths.root)
    paths.ticket_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(paths.ticket, text)
    return f'wrote {paths.ticket.relative_to(paths.root)}; review it, then run validate\n'


def run_validate(options: argparse.Namespace, cwd: Path) -> str:
    paths = Paths(root=repository_root(cwd), slug=options.slug)
    if not paths.ticket.is_file():
        raise MissingTicketError(paths.ticket)
    tree = parse(paths.ticket.read_text(encoding='utf-8'))
    validate_tree(tree, paths)
    ensure_excluded(paths.root)
    existing = read_work_unit(paths)
    investigations = linked_investigations(existing, tree)
    status = existing.get('status', 'staged')
    unit = {
        **existing,
        'schema': SCHEMA_VERSION,
        'slug': paths.slug,
        'status': status,
        'ticket': ticket_section(tree, paths),
        'investigations': investigations,
    }
    atomic_write(paths.work_unit, json.dumps(unit, indent=2) + '\n')
    relative = paths.work_unit.relative_to(paths.root)
    linked = len(investigations)
    return f'valid; staged {relative} (status {status}, {linked} investigations)\n'


HANDLERS: dict[Command, Callable[[argparse.Namespace, Path], str]] = {
    Command.WRITE: run_write,
    Command.VALIDATE: run_validate,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='ticket_state.py', description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest='command', required=True)
    for command in Command:
        commands.add_parser(command).add_argument('--slug', required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        output = HANDLERS[Command(options.command)](options, Path.cwd())
    except TicketError as error:
        sys.stderr.write(f'error: {error}\n')
        return EXIT_REJECTED
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
