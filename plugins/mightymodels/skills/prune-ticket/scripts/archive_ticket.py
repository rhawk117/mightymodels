"""Close a mightymodels ticket into a bounded archive, then prune its working state.

`check` lists live work that blocks closing. `close` refuses while any remains, compacts
the ticket's durable state (tasks, verification contract and results, ledger decisions,
review decisions, worker receipts) into archives/SLUG.md (30 lines at most) and a JSON
sidecar, verifies both, and marks the work unit closed. `prune` shows what it would remove
and, with --confirm, deletes the ticket directory, the ledgers no other ticket links, and
the ticket's worker receipts. Nothing is deleted unless the archive was written and read
back.

Usage:
    python3 archive_ticket.py check --slug SLUG
    python3 archive_ticket.py close --slug SLUG  < closing.json
    python3 archive_ticket.py prune --slug SLUG [--confirm]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

SCHEMA_VERSION = 1
EXIT_BLOCKED = 1
EXIT_REJECTED = 2
ARCHIVE_LINES = 30
DECISION_LIMIT = 4
GOTCHA_LIMIT = 3
RECENT_RECEIPTS = 10
RECENT_ANSWERS = 10
SUBAGENTS = 'subagents'
DECISIONS = 'decisions'
RECEIPT_KINDS: dict[str, str] = {
    SUBAGENTS: 'worker receipts',
    DECISIONS: 'recorded answers',
}
SHORT_SHA = 12
EXCLUDE_LINE = '.mightymodels/'
SAFE_SLUG = re.compile(r'^[a-z0-9][a-z0-9-]*$')
SAFE_REVISION = re.compile(r'^[0-9A-Za-z][0-9A-Za-z._/-]*$')
PLAN_TASK = re.compile(r'^T\d+$')
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

type Json = dict[str, object]


class Command(StrEnum):
    CHECK = 'check'
    CLOSE = 'close'
    PRUNE = 'prune'


class ArchiveError(Exception):
    pass


class StateUnreadableError(ArchiveError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f'{path}: {reason}; repair the state before closing or pruning')


class NoRepositoryError(ArchiveError):
    def __init__(self, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


class InvalidSlugError(ArchiveError):
    def __init__(self, slug: str) -> None:
        super().__init__(f'{slug!r} is not a ticket slug')


class NotStagedError(ArchiveError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} does not exist; there is no staged ticket to close')


class ClosingInputError(ArchiveError):
    def __init__(self, reason: str) -> None:
        super().__init__(f'stdin: {reason}')


class NotClosedError(ArchiveError):
    def __init__(self, slug: str) -> None:
        super().__init__(
            f'{slug} is not closed with a readable archive; run close first, nothing was deleted'
        )


class ArchiveUnreadableError(ArchiveError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f'{path} failed its read-back ({reason}); nothing was deleted')


class UnsafeTargetError(ArchiveError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} is not a plain ticket directory; refusing to delete it')


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path
    slug: str

    @property
    def base(self) -> Path:
        return self.root / '.mightymodels'

    @property
    def ticket(self) -> Path:
        return self.base / self.slug

    @property
    def unit(self) -> Path:
        return self.ticket / 'work-unit.json'

    @property
    def runtime(self) -> Path:
        return self.base / '.runtime'

    def receipts(self, kind: str) -> Path:
        return self.runtime / kind / 'receipts.jsonl'

    @property
    def archives(self) -> Path:
        return self.base / 'archives'


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


def head_ref(root: Path) -> str | None:
    head = read_text(git_dir(root) / 'HEAD')
    return head.removeprefix('ref:').strip() if head and head.startswith('ref:') else None


def resolve_head(root: Path) -> str | None:
    directory = git_dir(root)
    head = read_text(directory / 'HEAD')
    if head is None or not head.startswith('ref:'):
        return head
    ref = head.removeprefix('ref:').strip()
    shared = common_dir(directory)
    return read_text(directory / ref) or read_text(shared / ref) or packed_ref(shared, ref)


def ensure_excluded(root: Path) -> None:
    exclude = common_dir(git_dir(root)) / 'info' / 'exclude'
    current = exclude.read_text(encoding='utf-8') if exclude.is_file() else ''
    if EXCLUDE_LINE in current.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = '' if not current or current.endswith('\n') else '\n'
    exclude.write_text(f'{current}{separator}{EXCLUDE_LINE}\n', encoding='utf-8')


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    program = shutil.which('git')
    if program is None:
        return None
    return subprocess.run(  # noqa: S603 - fixed git argv; the only variable is a validated branch name
        [program, *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def redact(text: str) -> str:
    for name, pattern in SECRET_PATTERNS.items():
        text = pattern.sub(f'[REDACTED:{name}]', text)
    return text


def mapping(value: object) -> Json:
    return value if isinstance(value, dict) else {}


def listing(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def short(sha: object) -> str:
    return str(sha)[:SHORT_SHA] if sha else 'unknown'


def load_json(path: Path) -> Json:
    if not path.is_file():
        if path.exists():
            raise StateUnreadableError(path, 'expected a regular JSON file')

        return {}

    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise StateUnreadableError(path, 'not readable JSON') from error

    if (
        not isinstance(raw, dict)
        or type(raw.get('schema')) is not int
        or raw['schema'] != SCHEMA_VERSION
    ):
        raise StateUnreadableError(path, 'expected a schema-1 object')
    return raw


def load_records(path: Path) -> list[Json]:
    if not path.is_file():
        if path.exists():
            raise StateUnreadableError(path, 'expected a regular record file')
        return []

    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except UnicodeError as error:
        raise StateUnreadableError(path, 'not readable UTF-8') from error

    records = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue

        record = parse_record(line)
        if record is None:
            raise StateUnreadableError(path, f'unreadable or unsupported record on line {number}')

        records.append(record)

    return records


def parse_record(line: str) -> Json | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    if (
        isinstance(record, dict)
        and type(record.get('schema', SCHEMA_VERSION)) is int
        and record.get('schema', SCHEMA_VERSION) == SCHEMA_VERSION
    ):
        return record
    return None


def replace(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def paths_for(slug: str) -> Paths:
    if not SAFE_SLUG.match(slug):
        raise InvalidSlugError(slug)
    return Paths(repository_root(Path.cwd()), slug)


def load_unit(paths: Paths) -> Json:
    if not paths.unit.is_file():
        raise NotStagedError(paths.unit)

    unit = load_json(paths.unit)
    if unit.get('status') not in ('staged', 'in-progress', 'closed') or not isinstance(
        unit.get('ticket'), dict
    ):
        raise StateUnreadableError(paths.unit, 'invalid ticket status or metadata')


    progress = unit.get('progress', {})
    if not isinstance(progress, dict) or not isinstance(progress.get('tasks', {}), dict):
        raise StateUnreadableError(paths.unit, 'progress.tasks must be an object')

    for task_id, entry in progress.get('tasks', {}).items():
        if (
            not re.fullmatch(r'[TCR]\d+', task_id)
            or not isinstance(entry, dict)
            or entry.get('status')
            not in ('pending', 'in-progress', 'verified', 'failed', 'blocked')
        ):
            raise StateUnreadableError(paths.unit, f'invalid task {task_id}')

    if not isinstance(unit.get('investigations', []), list) or any(
        not isinstance(item, str) for item in unit.get('investigations', [])
    ):
        raise StateUnreadableError(paths.unit, 'investigations must be a list of identifiers')

    return unit


def contract_commands(paths: Paths) -> dict[str, Json]:
    path = paths.ticket / 'verification' / 'contract.json'
    contract = load_json(path)
    if not contract:
        return {}

    commands = contract.get('commands')
    if not isinstance(commands, dict) or any(
        not isinstance(entry, dict) or entry.get('id') != key for key, entry in commands.items()
    ):
        raise StateUnreadableError(path, 'commands must map identifiers to command objects')
    return commands


def latest_receipts(paths: Paths) -> dict[str, Json]:
    path = paths.ticket / 'verification' / 'receipts.jsonl'
    records = load_records(path)
    if any(
        not isinstance(record.get('id'), str)
        or record.get('outcome') not in ('pass', 'fail', 'timeout', 'not-found')
        for record in records
    ):
        raise StateUnreadableError(path, 'invalid verification receipt')

    return {str(record.get('id')): record for record in records}


def tasks_of(unit: Json) -> dict[str, Json]:
    tasks = mapping(mapping(unit.get('progress')).get('tasks'))
    return {task_id: mapping(entry) for task_id, entry in tasks.items()}


def latest_review(paths: Paths) -> Path | None:
    runs = sorted((paths.ticket / 'review').glob('*/review-run.json'))
    return runs[-1].parent if runs else None


def task_blockers(paths: Paths, unit: Json) -> list[str]:
    tasks = tasks_of(unit)
    planned = {command.split('.', 1)[0] for command in contract_commands(paths)}
    never = sorted(t for t in planned - set(tasks) if PLAN_TASK.match(t))
    blockers = [f'{task} has contract commands but was never started' for task in never]
    if not tasks:
        blockers.append('no verified task work is recorded')

    blockers.extend(
        f'{task_id} is {entry.get("status")}, not verified'
        for task_id, entry in sorted(tasks.items())
        if entry.get('status') != 'verified'
    )
    return blockers


def review_blockers(paths: Paths) -> list[str]:
    review_root = paths.ticket / 'review'
    directories = {
        path.parent
        for pattern in ('*/review-run.json', '*/findings.jsonl')
        for path in review_root.glob(pattern)
    }

    for review in directories:
        run_path = review / 'review-run.json'
        if not run_path.is_file():
            raise StateUnreadableError(run_path, 'review metadata is missing')

        load_json(run_path)
        load_records(review / 'findings.jsonl')

    directory = latest_review(paths)
    if directory is None:
        return []

    run = load_json(directory / 'review-run.json')
    findings_path = directory / 'findings.jsonl'
    if not findings_path.is_file():
        raise StateUnreadableError(findings_path, 'review findings are missing')

    records = load_records(findings_path)
    if any(not isinstance(record.get('id'), str) for record in records):
        raise StateUnreadableError(findings_path, 'finding identifiers are missing')

    findings = {str(r['id']) for r in records}
    dispositions = mapping(run.get('dispositions'))
    outcomes = mapping(run.get('outcomes'))

    if any(
        not isinstance(run.get(field), dict)
        or any(not isinstance(entry, dict) for entry in run[field].values())
        for field in ('dispositions', 'outcomes')
    ):
        raise StateUnreadableError(
            directory / 'review-run.json', 'invalid dispositions or outcomes'
        )

    if any(
        entry.get('decision') not in ('fix', 'defer', 'accept-risk', 'dismiss')
        for entry in dispositions.values()
    ) or any(
        entry.get('result') not in ('fixed', 'failed', 'blocked') for entry in outcomes.values()
    ):
        raise StateUnreadableError(
            directory / 'review-run.json', 'unknown decision or remediation result'
        )

    undecided = sorted(findings - set(dispositions))
    unfixed = sorted(
        finding_id
        for finding_id, entry in dispositions.items()
        if mapping(entry).get('decision') == 'fix'
        and mapping(outcomes.get(finding_id)).get('result') != 'fixed'
    )
    blockers = [f'review finding {f} has no decision' for f in undecided]
    blockers.extend(f'review finding {f} was chosen for fixing and is not fixed' for f in unfixed)
    return blockers


def branch_blockers(paths: Paths, unit: Json) -> list[str]:
    branch = str(mapping(unit.get('ticket')).get('branch') or '')
    if not SAFE_REVISION.match(branch):
        return []

    exists = git(paths.root, 'rev-parse', '--verify', '--quiet', f'refs/heads/{branch}')
    if exists is None or exists.returncode != 0:
        return []

    ahead = git(paths.root, 'rev-list', '--count', f'refs/heads/{branch}', '--not', '--remotes')
    blockers = []
    if ahead is not None and ahead.returncode == 0 and ahead.stdout.strip() != '0':
        blockers.append(f'branch {branch} has {ahead.stdout.strip()} commits on no remote')

    if head_ref(paths.root) == f'refs/heads/{branch}':
        dirty = git(paths.root, 'status', '--porcelain', '--untracked-files=no')
        if dirty is not None and dirty.stdout.strip():
            blockers.append(f'branch {branch} is checked out with uncommitted changes')

    return blockers


def live_work(paths: Paths, unit: Json) -> list[str]:
    blockers = task_blockers(paths, unit)
    if (paths.ticket / 'whats-broken.md').is_file():
        blockers.append('whats-broken.md is present: a debug is still live')

    blockers.extend(review_blockers(paths))
    blockers.extend(branch_blockers(paths, unit))
    # Read every source the archive/deletion consumes before any mutation.
    latest_receipts(paths)
    for kind in RECEIPT_KINDS:
        load_records(paths.receipts(kind))

    for investigation in listing(unit.get('investigations')):
        load_records(paths.runtime / 'investigations' / f'{investigation}.jsonl')

    return blockers


def run_check(options: argparse.Namespace) -> tuple[str, int]:
    paths = paths_for(options.slug)
    blockers = live_work(paths, load_unit(paths))
    if blockers:
        return 'live work remains\n' + ''.join(f'  - {b}\n' for b in blockers), EXIT_BLOCKED

    return f'{paths.slug} has no live work\n', 0


@dataclass(frozen=True, slots=True)
class Closing:
    shipped: str
    pr: str | None
    gotchas: list[str]


def one_line(value: object) -> str:
    return redact(' '.join(str(value).split()))


def read_closing() -> Closing:
    try:
        raw = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        message = 'a JSON object with shipped, pr, and gotchas'
        raise ClosingInputError(message) from error

    payload = mapping(raw)
    shipped = one_line(payload.get('shipped', ''))
    if not shipped:
        message = 'shipped is required: what this ticket delivered, one line'
        raise ClosingInputError(message)

    gotchas = [one_line(item) for item in listing(payload.get('gotchas')) if str(item).strip()]
    if len(gotchas) > GOTCHA_LIMIT:
        message = f'at most {GOTCHA_LIMIT} gotchas; the rest belong in the docs or nowhere'
        raise ClosingInputError(message)

    pr = one_line(payload['pr']) if payload.get('pr') else None
    return Closing(shipped, pr, gotchas)


def verification_record(paths: Paths) -> list[Json]:
    latest = latest_receipts(paths)
    return [
        {
            'id': command_id,
            'argv': listing(command.get('argv')),
            'expect_exit': command.get('expect_exit', 0),
            'outcome': latest.get(command_id, {}).get('outcome', 'never-run'),
            'head': latest.get(command_id, {}).get('head'),
            'digest': latest.get(command_id, {}).get('digest'),
        }
        for command_id, command in sorted(contract_commands(paths).items())
    ]


def live_ledger_entries(path: Path) -> list[Json]:
    records = load_records(path)
    retired = {seq for record in records for seq in listing(record.get('supersedes'))}
    return [record for record in records if record.get('seq') not in retired]


def ledger_decisions(paths: Paths, unit: Json) -> list[Json]:
    decisions = [
        {
            'text': one_line(record.get('text', '')),
            'from': f'{investigation} e{record.get("seq")}',
        }
        for investigation in listing(unit.get('investigations'))
        for record in live_ledger_entries(
            paths.runtime / 'investigations' / f'{investigation}.jsonl'
        )
        if record.get('kind') == 'decision'
    ]
    return decisions[-DECISION_LIMIT:]


def review_record(paths: Paths) -> Json:
    directory = latest_review(paths)
    if directory is None:
        return {}

    run = load_json(directory / 'review-run.json')
    outcomes = mapping(run.get('outcomes'))
    by_decision: dict[str, list[str]] = {}
    for finding_id, entry in mapping(run.get('dispositions')).items():
        decision = str(mapping(entry).get('decision'))
        fixed = mapping(outcomes.get(finding_id)).get('result') == 'fixed'
        by_decision.setdefault('fixed' if fixed else decision, []).append(finding_id)

    reasons = {
        finding_id: one_line(mapping(entry).get('reason', ''))
        for finding_id, entry in mapping(run.get('dispositions')).items()
        if mapping(entry).get('reason')
    }
    findings = {str(r.get('id')) for r in load_records(directory / 'findings.jsonl')}
    return {
        'run': run.get('run'),
        'depth': run.get('depth'),
        'findings': len(findings),
        'by_decision': by_decision,
        'reasons': reasons,
    }


def ticket_receipts(paths: Paths, kind: str) -> list[Json]:
    records = load_records(paths.receipts(kind))
    return [record for record in records if record.get('ticket') == paths.slug]


def answers_record(paths: Paths) -> Json:
    answers = ticket_receipts(paths, DECISIONS)
    recent = [
        {'id': r.get('id'), 'question': r.get('question'), 'answer': r.get('answer')}
        for r in answers[-RECENT_ANSWERS:]
    ]
    return {'recorded': len(answers), 'recent': recent}


def latest_per_agent(receipts: list[Json]) -> list[Json]:
    keyed = {
        str(record.get('agent_id') or f'#{index}'): record for index, record in enumerate(receipts)
    }
    return list(keyed.values())


def agents_record(paths: Paths) -> Json:
    receipts = latest_per_agent(ticket_receipts(paths, SUBAGENTS))
    counts = Counter(f'{r.get("agent")} {r.get("status")}' for r in receipts)
    recent = [
        {'agent': r.get('agent'), 'status': r.get('status'), 'at': r.get('at')}
        for r in receipts[-RECENT_RECEIPTS:]
    ]
    return {
        'runs': len(receipts),
        'by_status': dict(sorted(counts.items())),
        'recent': recent,
    }


def tasks_record(unit: Json) -> dict[str, Json]:
    return {
        task_id: {'status': entry.get('status'), 'attempts': entry.get('attempts', {})}
        for task_id, entry in sorted(tasks_of(unit).items())
    }


def build_record(paths: Paths, unit: Json, closing: Closing) -> Json:
    ticket = mapping(unit.get('ticket'))
    return {
        'schema': SCHEMA_VERSION,
        'slug': paths.slug,
        'closed_at': now(),
        'head': resolve_head(paths.root),
        'shipped': closing.shipped,
        'pr': closing.pr,
        'tracker': ticket.get('tracker'),
        'summary': ticket.get('summary'),
        'investigations': listing(unit.get('investigations')),
        'tasks': tasks_record(unit),
        'verification': verification_record(paths),
        'decisions': ledger_decisions(paths, unit),
        'review': review_record(paths),
        'agents': agents_record(paths),
        'answers': answers_record(paths),
        'gotchas': closing.gotchas,
    }


def tracker_text(tracker: object) -> str:
    parts = mapping(tracker)
    issue = f'#{parts["issue"]}' if parts.get('issue') else ''
    return ' '.join(filter(None, (issue, str(parts.get('jira') or '')))) or 'none'


def attempts_text(attempts: object) -> str:
    return ', '.join(f'{worker} {count}' for worker, count in mapping(attempts).items())


def tasks_line(record: Json) -> str:
    tasks = mapping(record['tasks'])
    items = [
        f'{task_id} ({attempts_text(mapping(entry).get("attempts"))})'
        for task_id, entry in tasks.items()
    ]
    return f'tasks: {"; ".join(items) or "none recorded"}'


def checks_line(record: Json) -> str:
    commands = [mapping(c) for c in listing(record['verification'])]
    failing = [str(c['id']) for c in commands if c.get('outcome') != 'pass']
    passed = len(commands) - len(failing)
    tail = f'; not passing: {", ".join(failing)}' if failing else ''
    return f'checks: {len(commands)} contract commands, {passed} passing at last run{tail}'


def review_line(record: Json) -> str:
    review = mapping(record['review'])
    if not review:
        return 'review: none'

    groups = mapping(review.get('by_decision'))
    parts = [f'{key} {", ".join(map(str, listing(ids)))}' for key, ids in groups.items()]
    detail = '; '.join(parts) or 'no decisions'
    run = f'run {review["run"]} ({review["depth"]})'
    return f'review: {run}, {review["findings"]} findings; {detail}'


def agents_line(record: Json) -> str:
    agents = mapping(record['agents'])
    counts = mapping(agents.get('by_status'))
    detail = ', '.join(f'{key} {value}' for key, value in counts.items())
    return f'agents: {agents.get("runs", 0)} runs' + (f' ({detail})' if detail else '')


def answers_line(record: Json) -> str:
    answers = mapping(record['answers'])
    return f'answers: {answers.get("recorded", 0)} recorded through ask_user'


def render_archive(record: Json) -> str:
    decisions = [
        f'- {mapping(d)["text"]} ({mapping(d)["from"]})' for d in listing(record['decisions'])
    ]
    accepted = [
        f'- review {finding_id}: {reason}'
        for finding_id, reason in mapping(mapping(record['review']).get('reasons')).items()
    ][: DECISION_LIMIT - len(decisions)]

    gotchas = [f'- {g}' for g in listing(record['gotchas'])]
    lines = [
        f'# {record["slug"]}',
        (
            f'shipped: {record["shipped"]} · PR: {record["pr"] or "none"} · '
            f'tracker: {tracker_text(record["tracker"])} · '
            f'pruned: {str(record["closed_at"])[:10]} · head: {short(record["head"])}'
        ),
        tasks_line(record),
        checks_line(record),
        review_line(record),
        agents_line(record),
        answers_line(record),
        'decisions:',
        *(decisions + accepted or ['- none recorded']),
        'gotchas:',
        *(gotchas or ['- none recorded']),
        f'details: archives/{record["slug"]}.json',
    ]
    return '\n'.join(lines) + '\n'


def archive_paths(paths: Paths) -> tuple[Path, Path]:
    stem = paths.slug
    suffix = 2
    while (paths.archives / f'{stem}.md').exists():
        stem = f'{paths.slug}-{suffix}'
        suffix += 1
        
    return paths.archives / f'{stem}.md', paths.archives / f'{stem}.json'


def verify_archive(markdown: Path, sidecar: Path) -> None:
    text = read_text(markdown)
    if text is None:
        raise ArchiveUnreadableError(markdown, 'missing')
    if len(text.splitlines()) > ARCHIVE_LINES:
        raise ArchiveUnreadableError(markdown, f'over {ARCHIVE_LINES} lines')
    try:
        record = json.loads(sidecar.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ArchiveUnreadableError(sidecar, 'not readable JSON') from error
    if mapping(record).get('schema') != SCHEMA_VERSION:
        raise ArchiveUnreadableError(sidecar, 'wrong schema')


def run_close(options: argparse.Namespace) -> tuple[str, int]:
    paths = paths_for(options.slug)
    unit = load_unit(paths)
    blockers = live_work(paths, unit)
    if blockers:
        lines = ''.join(f'  - {b}\n' for b in blockers)
        return f'not closed; live work remains\n{lines}', EXIT_BLOCKED
    closing = read_closing()
    record = build_record(paths, unit, closing)
    markdown, sidecar = archive_paths(paths)
    ensure_excluded(paths.root)
    replace(sidecar, json.dumps(record, indent=2) + '\n')
    replace(markdown, render_archive(record))
    verify_archive(markdown, sidecar)
    unit.update(
        {
            'status': 'closed',
            'closed_at': record['closed_at'],
            'archive': str(markdown.relative_to(paths.root)),
        }
    )
    replace(paths.unit, json.dumps(unit, indent=2) + '\n')
    return f'closed {paths.slug}; archive at {markdown.relative_to(paths.root)}\n', 0


@dataclass(frozen=True, slots=True)
class Removal:
    ticket: Path
    ledgers: list[Path]
    kept_ledgers: list[str]
    receipts: dict[str, int]


def other_links(paths: Paths) -> set[str]:
    links: set[str] = set()
    for unit_file in paths.base.glob('*/work-unit.json'):
        if unit_file.parent.name == paths.slug:
            continue
        investigations = load_json(unit_file).get('investigations', [])
        if not isinstance(investigations, list) or any(
            not isinstance(item, str) for item in investigations
        ):
            raise StateUnreadableError(unit_file, 'investigations must be a list of identifiers')
        links.update(investigations)
    return links


def plan_removal(paths: Paths, unit: Json) -> Removal:
    shared = other_links(paths)
    linked = [str(item) for item in listing(unit.get('investigations'))]
    ledgers = [
        paths.runtime / 'investigations' / f'{investigation}.jsonl'
        for investigation in linked
        if investigation not in shared and SAFE_SLUG.match(investigation)
    ]
    return Removal(
        ticket=paths.ticket,
        ledgers=[ledger for ledger in ledgers if ledger.is_file()],
        kept_ledgers=sorted(set(linked) & shared),
        receipts={kind: len(ticket_receipts(paths, kind)) for kind in RECEIPT_KINDS},
    )


def closed_archive(paths: Paths, unit: Json) -> Path:
    archive = unit.get('archive')
    if unit.get('status') != 'closed' or not isinstance(archive, str):
        raise NotClosedError(paths.slug)
    markdown = paths.root / archive
    verify_archive(markdown, markdown.with_suffix('.json'))
    return markdown


# Same sidecar-lock protocol as src/mightymodels_plugin/receipt_lock.py;
# this script remains runnable with the standard library alone.
@contextmanager
def receipt_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + '.lock').open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt

            if handle.seek(0, 2) == 0:
                handle.write(b'\0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def drop_receipts(paths: Paths, kind: str) -> None:
    source = paths.receipts(kind)
    with receipt_lock(source):
        if not source.is_file():
            return
        records = load_records(source)
        kept = [record for record in records if record.get('ticket') != paths.slug]
        replace(source, ''.join(json.dumps(record) + '\n' for record in kept))


def safe_ticket_dir(paths: Paths) -> Path:
    target = paths.ticket
    if target.is_symlink() or target.resolve().parent != paths.base.resolve():
        raise UnsafeTargetError(target)
    return target


def describe(removal: Removal, root: Path) -> str:
    lines = [f'  - {removal.ticket.relative_to(root)}/ (the whole ticket directory)']
    lines.extend(f'  - {ledger.relative_to(root)}' for ledger in removal.ledgers)
    lines.extend(
        f'  - {count} {RECEIPT_KINDS[kind]} tagged with this ticket'
        for kind, count in removal.receipts.items()
        if count
    )
    lines.extend(f'  - kept {ledger}: another ticket links it' for ledger in removal.kept_ledgers)
    return ''.join(f'{line}\n' for line in lines)


def run_prune(options: argparse.Namespace) -> tuple[str, int]:
    paths = paths_for(options.slug)
    unit = load_unit(paths)
    archive = closed_archive(paths, unit)
    blockers = live_work(paths, unit)
    if blockers:
        return 'not pruned; live work remains\n' + ''.join(
            f'  - {b}\n' for b in blockers
        ), EXIT_BLOCKED
    removal = plan_removal(paths, unit)
    listing_text = describe(removal, paths.root)
    if not options.confirm:
        return f'would remove (run again with --confirm):\n{listing_text}', 0
    target = safe_ticket_dir(paths)
    for kind in RECEIPT_KINDS:
        drop_receipts(paths, kind)
    for ledger in removal.ledgers:
        ledger.unlink()
    shutil.rmtree(target)
    relative = archive.relative_to(paths.root)
    return f'pruned {paths.slug}; the archive stays at {relative}\n{listing_text}', 0


HANDLERS: dict[Command, Callable[[argparse.Namespace], tuple[str, int]]] = {
    Command.CHECK: run_check,
    Command.CLOSE: run_close,
    Command.PRUNE: run_prune,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='archive_ticket.py', description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest='command', required=True)
    check = commands.add_parser(Command.CHECK, help='list live work that blocks closing')
    close = commands.add_parser(Command.CLOSE, help='write the archive and close the unit')
    prune = commands.add_parser(Command.PRUNE, help='delete the closed ticket state')
    prune.add_argument('--confirm', action='store_true')
    for sub in (check, close, prune):
        sub.add_argument('--slug', required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        output, code = HANDLERS[Command(options.command)](options)
    except (ArchiveError, OSError) as error:
        sys.stderr.write(f'error: {error}\n')
        return EXIT_REJECTED
    sys.stdout.write(output)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
