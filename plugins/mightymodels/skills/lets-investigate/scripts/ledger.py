"""Append-only investigation ledger for the lets-investigate skill.

Each investigation is one schema-versioned JSONL file. Records are validated and
redacted before any of them is written, and prior records are never rewritten: an entry
is retired by a later entry that names it in ``supersedes``.

Usage:
    python3 ledger.py start --target TEXT --kind {behavior,claim,research}
    python3 ledger.py add --id ID --round N  < entries.json
    python3 ledger.py render --id ID
    python3 ledger.py knowns --id ID [--kind KIND ...] [--limit N]
    python3 ledger.py list
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

SCHEMA_VERSION = 1
EXCLUDE_LINE = '.mightymodels/'
SLUG_LIMIT = 40
TABLE_LIMIT = 40
SHORT_SHA = 12
EXIT_REJECTED = 2


class EntryKind(StrEnum):
    TARGET = 'target'
    KNOWN = 'known'
    OPEN = 'open'
    DECISION = 'decision'
    RESOURCE = 'resource'
    NEXT = 'next'


class TargetKind(StrEnum):
    BEHAVIOR = 'behavior'
    CLAIM = 'claim'
    RESEARCH = 'research'


class Source(StrEnum):
    CODE_SCOUT = 'code-scout'
    WEB_SCOUT = 'web-scout'
    USER = 'user'
    PRIMARY = 'primary'


class Command(StrEnum):
    START = 'start'
    ADD = 'add'
    RENDER = 'render'
    KNOWNS = 'knowns'
    LIST = 'list'


@dataclass(frozen=True, slots=True)
class Rule:
    needs_cite: bool
    sources: frozenset[Source]


ANY_SOURCE = frozenset(Source)
TABLE_KINDS = ('known', 'open', 'decision', 'resource')
RULES: dict[EntryKind, Rule] = {
    EntryKind.KNOWN: Rule(needs_cite=True, sources=ANY_SOURCE),
    EntryKind.OPEN: Rule(needs_cite=False, sources=ANY_SOURCE),
    EntryKind.DECISION: Rule(needs_cite=False, sources=frozenset({Source.USER})),
    EntryKind.RESOURCE: Rule(needs_cite=True, sources=ANY_SOURCE),
    EntryKind.NEXT: Rule(
        needs_cite=False,
        sources=frozenset({Source.CODE_SCOUT, Source.WEB_SCOUT, Source.USER}),
    ),
}

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    'private-key': re.compile(
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
        re.DOTALL,
    ),
    'aws-key': re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_\w{20,})'),
    'slack-token': re.compile(r'\bxox[abposr]-[A-Za-z0-9-]{10,}'),
    'stripe-key': re.compile(r'\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b'),
    'api-key': re.compile(r'\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}'),
    'jwt': re.compile(r'\beyJ[\w-]+\.[\w-]+\.[\w-]+'),
    'bearer': re.compile(r'\bBearer [A-Za-z0-9._~+/-]{12,}=*'),
    'url-credentials': re.compile(r'(?<=://)[^/\s:@]+:[^@\s]+(?=@)'),
    'assignment': re.compile(
        r'(?i)[A-Z0-9_]*(?:password|passwd|secret|token|api[_-]?key)[A-Z0-9_]*'
        r'["\']?\s*[:=]\s*["\']?[^\s,;"\']+'
    ),
}


class LedgerError(Exception):
    pass


class UnsupportedSchemaError(LedgerError):
    def __init__(self, path: Path, line: int, version: object) -> None:
        super().__init__(
            f'{path}:{line}: schema {version!r} is not supported, expected {SCHEMA_VERSION}'
        )


class CorruptRecordError(LedgerError):
    def __init__(self, path: Path, line: int) -> None:
        super().__init__(f'{path}:{line}: not a valid ledger record')


class UnknownInvestigationError(LedgerError):
    def __init__(self, investigation: str) -> None:
        super().__init__(f'no investigation named {investigation!r}; run list')


class InvalidEntryError(LedgerError):
    def __init__(self, index: int, reason: str) -> None:
        super().__init__(f'entry {index}: {reason}')


class RoundRegressionError(LedgerError):
    def __init__(self, given: int, latest: int) -> None:
        super().__init__(f'round {given} is earlier than the latest round {latest}')


@dataclass(frozen=True, slots=True)
class Record:
    seq: int
    round: int
    kind: EntryKind
    text: str
    source: Source
    cite: str | None = None
    supersedes: tuple[int, ...] = ()
    at: str = ''
    head: str | None = None
    schema: int = SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class Redacted:
    text: str
    hits: int


@dataclass(slots=True)
class Ledger:
    path: Path
    records: list[Record] = field(default_factory=list)
    head: str | None = None

    @property
    def next_seq(self) -> int:
        return len(self.records) + 1

    @property
    def latest_round(self) -> int:
        return max((record.round for record in self.records), default=0)

    def live(self) -> list[Record]:
        retired = {seq for record in self.records for seq in record.supersedes}
        return [record for record in self.records if record.seq not in retired]


def now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec='seconds')


def redact(text: str) -> Redacted:
    hits = 0
    for name, pattern in SECRET_PATTERNS.items():
        text, count = pattern.subn(f'[REDACTED:{name}]', text)
        hits += count
    return Redacted(text=text, hits=hits)


def repository_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / '.git').exists():
            return candidate
    return None


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


def resolve_head(root: Path) -> str | None:
    directory = git_dir(root)
    head = read_text(directory / 'HEAD')
    if head is None or not head.startswith('ref:'):
        return head
    ref = head.removeprefix('ref:').strip()
    shared = common_dir(directory)
    return read_text(directory / ref) or read_text(shared / ref) or packed_ref(shared, ref)


def exclude_state(cwd: Path) -> None:
    root = repository_root(cwd)
    if root is None:
        return
    exclude = common_dir(git_dir(root)) / 'info' / 'exclude'
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')


def current_head(cwd: Path) -> str | None:
    root = repository_root(cwd)
    return None if root is None else resolve_head(root)


def state_dir(cwd: Path) -> Path:
    root = repository_root(cwd)
    if root is not None:
        return root / '.mightymodels' / '.runtime' / 'investigations'
    digest = hashlib.sha256(str(cwd).encode()).hexdigest()[:12]
    return Path.home() / '.local' / 'state' / 'mightymodels' / digest / 'investigations'


def slugify(text: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    if len(slug) > SLUG_LIMIT:
        slug = slug[: SLUG_LIMIT + 1].rsplit('-', 1)[0]
    return slug or 'investigation'


def record_from(raw: dict[str, object]) -> Record:
    return Record(
        seq=int(str(raw['seq'])),
        round=int(str(raw['round'])),
        kind=EntryKind(raw['kind']),
        text=str(raw['text']),
        source=Source(raw['source']),
        cite=None if raw.get('cite') is None else str(raw['cite']),
        supersedes=tuple(int(str(seq)) for seq in raw.get('supersedes') or ()),
        at=str(raw.get('at', '')),
        head=None if raw.get('head') is None else str(raw['head']),
    )


def parse_line(path: Path, number: int, line: str) -> Record:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as error:
        raise CorruptRecordError(path, number) from error
    if raw.get('schema') != SCHEMA_VERSION:
        raise UnsupportedSchemaError(path, number, raw.get('schema'))
    try:
        return record_from(raw)
    except (KeyError, ValueError) as error:
        raise CorruptRecordError(path, number) from error


def load(path: Path) -> Ledger:
    lines = path.read_text(encoding='utf-8').splitlines()
    records = [
        parse_line(path, number, line) for number, line in enumerate(lines, start=1) if line.strip()
    ]
    return Ledger(path=path, records=records)


def open_ledger(cwd: Path, investigation: str) -> Ledger:
    path = state_dir(cwd) / f'{investigation}.jsonl'
    if not path.is_file():
        raise UnknownInvestigationError(investigation)
    ledger = load(path)
    ledger.head = current_head(cwd)
    return ledger


def append(ledger: Ledger, records: Iterable[Record]) -> None:
    payload = ''.join(json.dumps(asdict(record)) + '\n' for record in records)
    ledger.path.parent.mkdir(parents=True, exist_ok=True)
    with ledger.path.open('a', encoding='utf-8') as handle:
        handle.write(payload)


def entry_error(ledger: Ledger, raw: dict[str, object]) -> str | None:
    kind = EntryKind(raw['kind'])
    rule = RULES.get(kind)
    if rule is None:
        return f'kind {kind} cannot be added; it is written by start'
    if rule.needs_cite and not raw.get('cite'):
        return f'a {kind} entry needs a cite (file:line, URL#heading, or path)'
    if Source(raw['source']) not in rule.sources:
        return f'a {kind} entry cannot come from {raw["source"]}'
    unknown = {int(str(seq)) for seq in raw.get('supersedes') or ()} - {
        record.seq for record in ledger.records if record.kind is not EntryKind.TARGET
    }
    return f'supersedes unknown entries {sorted(unknown)}' if unknown else None


def build_record(ledger: Ledger, raw: dict[str, object], offset: int) -> Record:
    candidate = {**raw, 'seq': ledger.next_seq + offset, 'at': now(), 'head': ledger.head}
    record = record_from(candidate)
    if not record.text.strip():
        raise InvalidEntryError(offset, 'text is empty')
    return record


@dataclass(frozen=True, slots=True)
class Batch:
    records: list[Record]
    redactions: int


def prepare(ledger: Ledger, round_number: int, entries: list[dict[str, object]]) -> Batch:
    if round_number < ledger.latest_round:
        raise RoundRegressionError(round_number, ledger.latest_round)
    records: list[Record] = []
    redactions = 0
    for offset, raw in enumerate(entries):
        try:
            reason = entry_error(ledger, raw)
            record = build_record(ledger, {**raw, 'round': round_number}, offset)
        except (KeyError, ValueError) as error:
            raise InvalidEntryError(offset, f'missing or invalid field: {error}') from error
        if reason is not None:
            raise InvalidEntryError(offset, reason)
        cleaned = redact(record.text)
        redactions += cleaned.hits
        records.append(Record(**{**asdict(record), 'text': cleaned.text}))
    return Batch(records=records, redactions=redactions)


def section(title: str, records: list[Record], kind: EntryKind) -> list[str]:
    lines = [f'### {title}']
    lines.extend(render_entry(record) for record in records if record.kind is kind)
    return [*lines, '']


def render_entry(record: Record) -> str:
    cite = f' [{record.cite}]' if record.cite else ''
    return f'- e{record.seq}: {record.text}{cite} ({record.source}, round {record.round})'


def render(ledger: Ledger) -> str:
    live = ledger.live()
    target = next(record for record in ledger.records if record.kind is EntryKind.TARGET)
    latest = ledger.latest_round
    current_next = [record for record in live if record.round == latest]
    lines = [f'## Ledger, round {latest}', f'Target: {target.text} ({target.cite})', '']
    lines += section('Knowns', live, EntryKind.KNOWN)
    lines += section('Open', live, EntryKind.OPEN)
    lines += section('Decisions', live, EntryKind.DECISION)
    lines += section('Resources', live, EntryKind.RESOURCE)
    lines += section('Next', current_next, EntryKind.NEXT)
    return '\n'.join(lines).rstrip() + '\n'


def table_cell(text: str | None) -> str:
    return (text or '').replace('|', '\\|')


def table_row(record: Record, head: str | None) -> str:
    status = 'current' if head is not None and record.head == head else 'lead'
    cells = [
        f'e{record.seq}',
        record.kind,
        table_cell(record.text),
        table_cell(record.cite),
        record.source,
        str(record.round),
        status,
    ]
    return '| ' + ' | '.join(cells) + ' |'


def knowns_table(ledger: Ledger, kinds: frozenset[EntryKind], limit: int) -> str:
    rows = [record for record in ledger.live() if record.kind in kinds]
    head = (ledger.head or 'unknown')[:SHORT_SHA]
    lines = [
        f'## Knowns table, {ledger.path.stem} at HEAD {head}',
        '| entry | kind | claim | cite | source | round | status |',
        '|---|---|---|---|---|---|---|',
        *(table_row(record, ledger.head) for record in rows[:limit]),
    ]
    if len(rows) > limit:
        lines.append(f'{len(rows) - limit} more rows; rerun with a larger --limit')
    return '\n'.join(lines) + '\n'


def unique_path(directory: Path, stem: str) -> Path:
    candidate = directory / f'{stem}.jsonl'
    suffix = 2
    while candidate.exists():
        candidate = directory / f'{stem}-{suffix}.jsonl'
        suffix += 1
    return candidate


def run_start(options: argparse.Namespace, cwd: Path) -> str:
    stamp = datetime.now(tz=UTC).strftime('%Y%m%d')
    exclude_state(cwd)
    directory = state_dir(cwd)
    directory.mkdir(parents=True, exist_ok=True)
    path = unique_path(directory, f'{stamp}-{slugify(options.target)}')
    cleaned = redact(options.target)
    target = Record(
        seq=1,
        round=0,
        kind=EntryKind.TARGET,
        text=cleaned.text,
        source=Source.USER,
        cite=str(TargetKind(options.kind)),
        at=now(),
        head=current_head(cwd),
    )
    append(Ledger(path=path), [target])
    return f'started {path.stem} at {path}\n'


def run_add(options: argparse.Namespace, cwd: Path) -> str:
    exclude_state(cwd)
    ledger = open_ledger(cwd, options.id)
    try:
        entries = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        raise InvalidEntryError(0, 'stdin is not a JSON array of entries') from error
    batch = prepare(ledger, options.round, list(entries))
    append(ledger, batch.records)
    saved = ' '.join(f'e{record.seq}' for record in batch.records)
    return f'saved {saved} to {ledger.path.stem} ({batch.redactions} redacted)\n'


def run_render(options: argparse.Namespace, cwd: Path) -> str:
    return render(open_ledger(cwd, options.id))


def run_knowns(options: argparse.Namespace, cwd: Path) -> str:
    kinds = frozenset(EntryKind(kind) for kind in options.kind or TABLE_KINDS)
    return knowns_table(open_ledger(cwd, options.id), kinds, options.limit)


def run_list(_options: argparse.Namespace, cwd: Path) -> str:
    directory = state_dir(cwd)
    rows = [
        f'{path.stem}\tround {load(path).latest_round}'
        for path in sorted(directory.glob('*.jsonl'))
    ]
    return '\n'.join(rows) + '\n' if rows else 'no investigations\n'


HANDLERS: dict[Command, Callable[[argparse.Namespace, Path], str]] = {
    Command.START: run_start,
    Command.ADD: run_add,
    Command.RENDER: run_render,
    Command.KNOWNS: run_knowns,
    Command.LIST: run_list,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='ledger.py', description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest='command', required=True)
    start = commands.add_parser(Command.START, help='open a new investigation')
    start.add_argument('--target', required=True)
    start.add_argument('--kind', required=True, choices=[kind.value for kind in TargetKind])
    add = commands.add_parser(Command.ADD, help='append a JSON array of entries from stdin')
    add.add_argument('--id', required=True)
    add.add_argument('--round', required=True, type=int)
    commands.add_parser(Command.RENDER, help='print the ledger').add_argument('--id', required=True)
    knowns = commands.add_parser(Command.KNOWNS, help='print the knowns table')
    knowns.add_argument('--id', required=True)
    knowns.add_argument('--kind', action='append', choices=TABLE_KINDS)
    knowns.add_argument('--limit', type=int, default=TABLE_LIMIT)
    commands.add_parser(Command.LIST, help='list investigations')
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        output = HANDLERS[Command(options.command)](options, Path.cwd())
    except LedgerError as error:
        sys.stderr.write(f'error: {error}\n')
        return EXIT_REJECTED
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
