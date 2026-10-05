"""Objective handoff snapshot for a mightymodels ticket, built only from durable files.

Reads the work unit, the linked investigation ledgers, the verification contract and
receipts, task transitions, the latest review run, and subagent receipts, and writes a
bounded snapshot.json and snapshot.md under the ticket's handoffs/ directory with atomic
replacement. A source that does not exist yet is read as empty. A record with a schema
version this script does not know is skipped and reported, never guessed at.

Usage:
    python3 snapshot.py write --slug SLUG [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

SCHEMA_VERSION = 1
EXIT_REJECTED = 2
DEFAULT_LIMIT = 8
SHORT_SHA = 12
EXCLUDE_LINE = '.mightymodels/'
SAFE_SLUG = re.compile(r'^[a-z0-9][a-z0-9-]*$')
PLAN_TASK = re.compile(r'^T\d+$')
STUCK = frozenset({'failed', 'blocked'})
SKIP_DECISIONS = frozenset({'fix'})

type Json = dict[str, object]


class SnapshotError(Exception):
    pass


class NoRepositoryError(SnapshotError):
    def __init__(self, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


class NotStagedError(SnapshotError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} does not exist; stage the ticket with open-ticket first')


class InvalidSlugError(SnapshotError):
    def __init__(self, slug: str) -> None:
        super().__init__(f'{slug!r} is not a ticket slug')


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path
    slug: str

    @property
    def ticket(self) -> Path:
        return self.root / '.mightymodels' / self.slug

    @property
    def runtime(self) -> Path:
        return self.root / '.mightymodels' / '.runtime'

    @property
    def handoffs(self) -> Path:
        return self.ticket / 'handoffs'


@dataclass(slots=True)
class Reader:
    warnings: list[str] = field(default_factory=list)

    def document(self, path: Path) -> Json:
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            self.warnings.append(f'{path.name} is not valid JSON; ignored')
            return {}
        return self.versioned(raw, path) or {}

    def records(self, path: Path) -> list[Json]:
        if not path.is_file():
            return []
        lines = path.read_text(encoding='utf-8').splitlines()
        parsed = (self.line(text, path) for text in lines if text.strip())
        return [record for record in parsed if record is not None]

    def line(self, text: str, path: Path) -> Json | None:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            self.warnings.append(f'{path.name}: a line is not valid JSON; ignored')
            return None
        return self.versioned(raw, path)

    def versioned(self, raw: object, path: Path) -> Json | None:
        if not isinstance(raw, dict):
            self.warnings.append(f'{path.name}: a record is not an object; ignored')
            return None
        version = raw.get('schema', SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            self.warnings.append(f'{path.name}: schema {version!r} is not supported; ignored')
            return None
        return raw


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


def packed_ref(directory: Path, ref: str) -> str | None:
    packed = read_text(directory / 'packed-refs') or ''
    matches = (
        line.split(' ', 1)[0]
        for line in packed.splitlines()
        if line.endswith(f' {ref}') and not line.startswith(('#', '^'))
    )
    return next(matches, None)


@dataclass(frozen=True, slots=True)
class Head:
    branch: str | None
    sha: str | None


def resolve_head(root: Path) -> Head:
    directory = git_dir(root)
    head = read_text(directory / 'HEAD')
    if head is None or not head.startswith('ref:'):
        return Head(branch=None, sha=head)
    ref = head.removeprefix('ref:').strip()
    shared = common_dir(directory)
    sha = read_text(directory / ref) or read_text(shared / ref) or packed_ref(shared, ref)
    return Head(branch=ref.removeprefix('refs/heads/'), sha=sha)


def ensure_excluded(root: Path) -> None:
    exclude = common_dir(git_dir(root)) / 'info' / 'exclude'
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')


def dirty_paths(root: Path) -> list[str] | None:
    git = shutil.which('git')
    if git is None:
        return None
    completed = subprocess.run(  # noqa: S603 - fixed git argv with no caller input
        [git, 'status', '--porcelain', '--untracked-files=normal'],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return [line[3:] for line in completed.stdout.splitlines() if line.strip()]


def mapping(value: object) -> Json:
    return value if isinstance(value, dict) else {}


def listing(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def short(sha: object) -> str:
    return str(sha)[:SHORT_SHA] if sha else 'unknown'


def repository_section(root: Path, head: Head, limit: int) -> Json:
    dirty = dirty_paths(root)
    return {
        'branch': head.branch,
        'head': head.sha,
        'dirty_count': None if dirty is None else len(dirty),
        'dirty': (dirty or [])[:limit],
    }


def contract_ids(paths: Paths, reader: Reader) -> dict[str, Json]:
    contract = reader.document(paths.ticket / 'verification' / 'contract.json')
    return {key: mapping(value) for key, value in mapping(contract.get('commands')).items()}


def latest_by(records: Iterable[Json], key: str) -> dict[str, Json]:
    return {str(record.get(key)): record for record in records}


def check_state(receipt: Json | None, head: str | None) -> str:
    if receipt is None:
        return 'never-run'
    outcome = str(receipt.get('outcome'))
    if receipt.get('head') != head:
        return f'stale ({outcome} at {short(receipt.get("head"))})'
    return outcome


@dataclass(frozen=True, slots=True)
class Sources:
    paths: Paths
    reader: Reader
    head: Head
    limit: int


def checks_section(sources: Sources) -> tuple[list[Json], list[Json]]:
    commands = contract_ids(sources.paths, sources.reader)
    receipts_file = sources.paths.ticket / 'verification' / 'receipts.jsonl'
    latest = latest_by(sources.reader.records(receipts_file), 'id')
    checks = [
        {'id': command_id, 'state': check_state(latest.get(command_id), sources.head.sha)}
        for command_id in sorted(commands)
    ]
    works = [
        {'id': command_id, 'argv': listing(commands[command_id].get('argv'))}
        for command_id in sorted(commands)
        if latest.get(command_id, {}).get('outcome') == 'pass'
    ]
    return checks, works[: sources.limit]


def tasks_section(unit: Json, checks: list[Json]) -> list[Json]:
    tasks = mapping(mapping(unit.get('progress')).get('tasks'))
    planned = {str(check['id']).split('.', 1)[0] for check in checks}
    rows: list[Json] = [
        {
            'task': task_id,
            'status': mapping(entry).get('status'),
            'attempts': mapping(entry).get('attempts', {}),
            'reasons': listing(mapping(entry).get('reasons')),
        }
        for task_id, entry in tasks.items()
    ]
    rows.extend(
        {'task': task_id, 'status': 'not started', 'attempts': {}, 'reasons': []}
        for task_id in sorted(planned - set(tasks))
        if PLAN_TASK.match(task_id)
    )
    return sorted(rows, key=task_order)


def task_order(row: Json) -> tuple[str, int]:
    task = str(row['task'])
    return task[0], int(task[1:]) if task[1:].isdigit() else 0


def do_not_retry(sources: Sources) -> list[Json]:
    transitions = sources.reader.records(sources.paths.ticket / 'transitions.jsonl')
    stuck = [
        {
            'task': record.get('task'),
            'to': record.get('to'),
            'reason': '; '.join(str(reason) for reason in listing(record.get('reasons'))),
            'head': short(record.get('head')),
            'at': record.get('at'),
        }
        for record in transitions
        if record.get('to') in STUCK
    ]
    return stuck[-sources.limit :]


def live_entries(records: list[Json]) -> list[Json]:
    retired = {seq for record in records for seq in listing(record.get('supersedes'))}
    return [record for record in records if record.get('seq') not in retired]


def ledger_entries(investigation: object, sources: Sources) -> list[Json]:
    path = sources.paths.runtime / 'investigations' / f'{investigation}.jsonl'
    if not path.is_file():
        sources.reader.warnings.append(f'investigation {investigation} is missing')
        return []
    return [
        {
            'kind': record.get('kind'),
            'text': record.get('text'),
            'cite': record.get('cite'),
            'from': f'{investigation} e{record.get("seq")}',
        }
        for record in live_entries(sources.reader.records(path))
    ]


def ledger_section(unit: Json, sources: Sources) -> tuple[list[Json], list[Json]]:
    entries = [
        entry
        for investigation in listing(unit.get('investigations'))
        for entry in ledger_entries(investigation, sources)
    ]
    decisions = [entry for entry in entries if entry['kind'] == 'decision']
    questions = [entry for entry in entries if entry['kind'] == 'open']
    return decisions[-sources.limit :], questions[-sources.limit :]


def latest_review(paths: Paths) -> Path | None:
    runs = sorted((paths.ticket / 'review').glob('*/review-run.json'))
    return runs[-1].parent if runs else None


def review_section(sources: Sources) -> Json:
    directory = latest_review(sources.paths)
    if directory is None:
        return {}
    run = sources.reader.document(directory / 'review-run.json')
    findings = latest_by(sources.reader.records(directory / 'findings.jsonl'), 'id')
    dispositions = mapping(run.get('dispositions'))
    outcomes = mapping(run.get('outcomes'))
    remediation = [
        finding_id
        for finding_id, entry in dispositions.items()
        if mapping(entry).get('decision') == 'fix'
        and mapping(outcomes.get(finding_id)).get('result') != 'fixed'
    ]
    decided = [
        {
            'finding': finding_id,
            'decision': mapping(entry).get('decision'),
            'reason': mapping(entry).get('reason'),
        }
        for finding_id, entry in dispositions.items()
        if mapping(entry).get('decision') not in SKIP_DECISIONS
    ]
    return {
        'run': run.get('run'),
        'depth': run.get('depth'),
        'head': short(run.get('head')),
        'findings': len(findings),
        'undecided': sorted(set(findings) - set(dispositions)),
        'remediation_open': remediation,
        'decisions': decided[: sources.limit],
    }


def subagent_section(sources: Sources) -> list[Json]:
    receipts = sources.reader.records(sources.paths.runtime / 'subagents' / 'receipts.jsonl')
    mine = [
        {
            'agent': record.get('agent'),
            'status': record.get('status'),
            'summary': record.get('summary'),
            'head': short(record.get('head')),
            'at': record.get('at'),
        }
        for record in latest_per_agent(receipts)
        if record.get('ticket') == sources.paths.slug
    ]
    return mine[-sources.limit :]


def answer_section(sources: Sources) -> list[Json]:
    receipts = sources.reader.records(sources.paths.runtime / 'decisions' / 'receipts.jsonl')
    mine = [
        {
            'id': record.get('id'),
            'question': record.get('question'),
            'answer': record.get('answer'),
            'at': record.get('at'),
        }
        for record in receipts
        if record.get('ticket') == sources.paths.slug
    ]
    return mine[-sources.limit :]


def latest_per_agent(receipts: list[Json]) -> list[Json]:
    keyed = {
        str(record.get('agent_id') or f'#{index}'): record for index, record in enumerate(receipts)
    }
    return list(keyed.values())


def load_unit(paths: Paths, reader: Reader) -> Json:
    path = paths.ticket / 'work-unit.json'
    if not path.is_file():
        raise NotStagedError(path)
    return reader.document(path)


def build(paths: Paths, limit: int) -> Json:
    reader = Reader()
    unit = load_unit(paths, reader)
    sources = Sources(paths, reader, resolve_head(paths.root), limit)
    checks, works = checks_section(sources)
    decisions, questions = ledger_section(unit, sources)
    ticket = mapping(unit.get('ticket'))
    return {
        'schema': SCHEMA_VERSION,
        'slug': paths.slug,
        'generated_at': now(),
        'ticket': {
            'summary': ticket.get('summary'),
            'status': unit.get('status'),
            'scope': ticket.get('scope'),
            'tracker': ticket.get('tracker'),
        },
        'repository': repository_section(paths.root, sources.head, limit),
        'tasks': tasks_section(unit, checks),
        'checks': checks,
        'works': works,
        'decisions': decisions,
        'open_questions': questions,
        'do_not_retry': do_not_retry(sources),
        'review': review_section(sources),
        'answers': answer_section(sources),
        'subagents': subagent_section(sources),
        'warnings': reader.warnings,
    }


def bullets(items: Iterable[str], empty: str) -> list[str]:
    lines = [f'- {item}' for item in items]
    return lines or [f'- {empty}']


def task_line(row: Json) -> str:
    attempts = ', '.join(f'{k} {v}' for k, v in mapping(row.get('attempts')).items())
    reasons = '; '.join(str(reason) for reason in listing(row.get('reasons')))
    detail = ' | '.join(part for part in (attempts, reasons) if part)
    return f'{row["task"]} {row["status"]}' + (f' ({detail})' if detail else '')


def cited(entry: Json) -> str:
    cite = f' [{entry["cite"]}]' if entry.get('cite') else ''
    return f'{entry.get("text")}{cite} ({entry.get("from")})'


def review_lines(review: Json) -> list[str]:
    if not review:
        return ['- no review run']
    lines = [
        (
            f'- run {review["run"]} ({review["depth"]}) at {review["head"]}: '
            f'{review["findings"]} findings'
        ),
        f'- undecided: {", ".join(listing(review["undecided"])) or "none"}',
        f'- remediation open: {", ".join(listing(review["remediation_open"])) or "none"}',
    ]
    lines.extend(
        f'- {mapping(item)["finding"]} {mapping(item)["decision"]}: '
        f'{mapping(item).get("reason") or "no reason"}'
        for item in listing(review.get('decisions'))
    )
    return lines


def header(snapshot: Json) -> list[str]:
    repository = mapping(snapshot['repository'])
    ticket = mapping(snapshot['ticket'])
    dirty = repository.get('dirty_count')
    tree = 'unknown' if dirty is None else ('clean' if dirty == 0 else f'{dirty} changed')
    return [
        f'# Snapshot for {snapshot["slug"]}',
        '',
        f'Generated {snapshot["generated_at"]} from durable files only.',
        f'Ticket: {ticket.get("summary")} (status {ticket.get("status")}).',
        (
            f'Repository: {repository.get("branch") or "detached"} at '
            f'{short(repository.get("head"))}; tree {tree}.'
        ),
        *(f'- changed: {path}' for path in listing(repository.get('dirty'))),
    ]


def check_line(check: Json) -> str:
    return f'{check["id"]} {check["state"]}'


def works_line(command: Json) -> str:
    argv = ' '.join(str(arg) for arg in listing(command['argv']))
    return f'{command["id"]}: `{argv}`'


def retry_line(entry: Json) -> str:
    return f'{entry["task"]} {entry["to"]} at {entry["head"]}: {entry["reason"]}'


def answer_line(receipt: Json) -> str:
    question = receipt.get('question') or 'question not recorded'
    return f'{receipt["id"]}: {question} -> {receipt.get("answer") or "no answer"}'


def subagent_line(receipt: Json) -> str:
    line = f'{receipt["agent"]} {receipt["status"]} at {receipt["head"]}'
    return f'{line}: {receipt["summary"]}' if receipt.get('summary') else line


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    key: str
    line: Callable[[Json], str]
    empty: str


SECTIONS = (
    Section('Tasks', 'tasks', task_line, 'none started'),
    Section('Checks at HEAD', 'checks', check_line, 'no contract'),
    Section('Works', 'works', works_line, 'no passing command yet'),
    Section('Decisions', 'decisions', cited, 'none recorded'),
    Section('Open questions', 'open_questions', cited, 'none recorded'),
    Section('Do not retry', 'do_not_retry', retry_line, 'no failed attempt recorded'),
    Section('Answers', 'answers', answer_line, 'no recorded answers'),
    Section('Subagents', 'subagents', subagent_line, 'no receipts yet'),
)


def section_lines(section: Section, snapshot: Json) -> list[str]:
    items = (section.line(mapping(item)) for item in listing(snapshot[section.key]))
    return ['', f'## {section.title}', '', *bullets(items, section.empty)]


def render(snapshot: Json) -> str:
    lines = header(snapshot)
    for section in SECTIONS:
        lines.extend(section_lines(section, snapshot))
    lines.extend(['', '## Review', '', *review_lines(mapping(snapshot['review']))])
    warnings = [str(warning) for warning in listing(snapshot['warnings'])]
    if warnings:
        lines.extend(['', '## Warnings', '', *bullets(warnings, '')])
    return '\n'.join(lines) + '\n'


def replace(path: Path, text: str) -> None:
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def run_write(options: argparse.Namespace) -> str:
    if not SAFE_SLUG.match(options.slug):
        raise InvalidSlugError(options.slug)
    paths = Paths(repository_root(Path.cwd()), options.slug)
    ensure_excluded(paths.root)
    snapshot = build(paths, options.limit)
    paths.handoffs.mkdir(parents=True, exist_ok=True)
    replace(paths.handoffs / 'snapshot.json', json.dumps(snapshot, indent=2) + '\n')
    replace(paths.handoffs / 'snapshot.md', render(snapshot))
    warnings = len(listing(snapshot['warnings']))
    relative = paths.handoffs.relative_to(paths.root)
    return f'wrote {relative}/snapshot.json and snapshot.md ({warnings} warnings)\n'


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='snapshot.py', description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest='command', required=True)
    write = commands.add_parser('write', help='write handoffs/snapshot.json and snapshot.md')
    write.add_argument('--slug', required=True)
    write.add_argument('--limit', type=int, default=DEFAULT_LIMIT)
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        output = run_write(options)
    except (SnapshotError, OSError) as error:
        sys.stderr.write(f'error: snapshot not written: {error}\n')
        return EXIT_REJECTED
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
