"""Per-task state for the mightymodels loop: gated, and durable before anything advances.

Every transition is checked, recorded in work-unit.json with an atomic replace, and
appended to transitions.jsonl before the caller may touch a brief or a checklist. A task
reaches verified only when every contract command for it passed at the current HEAD,
every other acceptance criterion carries a citation, and the commit touched only the
files the task owns. Plan tasks are T1, T2, ...; fixes for failing CI checks after the
sprint are C1, C2, ...; review remediation of finding Fn is Rn. All climb the same
engineer-then-architect ladder. `ready` is the gate before any push.

Usage:
    python3 task_state.py start --slug SLUG --task T1 --by engineer --owned PATH [...]
        [--expanded-envelope]
    python3 task_state.py verify --slug SLUG --task T1 --commit SHA [--brief PATH]
        [--assertion AC-2=path/to/file.py:41 ...]
    python3 task_state.py mark --slug SLUG --task T1 --to failed --reason TEXT
    python3 task_state.py show --slug SLUG
    python3 task_state.py ready --slug SLUG
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

SCHEMA_VERSION = 1
EXIT_BLOCKED = 1
EXIT_REJECTED = 2
ARCHITECT_LIMIT = 1
SAFE_REVISION = re.compile(r'^[0-9A-Za-z][0-9A-Za-z._/-]*$')
TASK_ID = re.compile(r'^[TCR]\d+$')
PLAN_TASK = 'T'
ASKED_CRITERION = re.compile(r'^\s*-\s*(AC-\d+)\s*:', re.MULTILINE)


class Command(StrEnum):
    START = 'start'
    VERIFY = 'verify'
    MARK = 'mark'
    SHOW = 'show'
    READY = 'ready'


class Status(StrEnum):
    PENDING = 'pending'
    IN_PROGRESS = 'in-progress'
    VERIFIED = 'verified'
    FAILED = 'failed'
    BLOCKED = 'blocked'


class Worker(StrEnum):
    ENGINEER = 'engineer'
    ARCHITECT = 'architect'


ALLOWED: dict[Status, frozenset[Status]] = {
    Status.PENDING: frozenset({Status.IN_PROGRESS}),
    Status.IN_PROGRESS: frozenset({Status.VERIFIED, Status.FAILED, Status.BLOCKED}),
    Status.FAILED: frozenset({Status.IN_PROGRESS}),
    Status.BLOCKED: frozenset({Status.IN_PROGRESS}),
    Status.VERIFIED: frozenset(),
}
MARKABLE = (Status.FAILED, Status.BLOCKED)
STUCK = frozenset(MARKABLE)


class TaskStateError(Exception):
    pass


class NoRepositoryError(TaskStateError):
    def __init__(self, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


class NotStagedError(TaskStateError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} does not exist; stage the ticket with open-ticket first')


class TransitionError(TaskStateError):
    def __init__(self, task: str, current: Status, target: Status) -> None:
        super().__init__(f'{task} cannot move from {current} to {target}')


class ArchitectSpentError(TaskStateError):
    def __init__(self, task: str) -> None:
        super().__init__(
            f'{task} already had its architect recovery; route it to whats-broken, '
            'or pass --expanded-envelope after the user approves a scope expansion'
        )


class UnsafeRevisionError(TaskStateError):
    def __init__(self, revision: str) -> None:
        super().__init__(f'{revision!r} is not a plain revision name')


class InvalidTaskError(TaskStateError):
    def __init__(self, task: str) -> None:
        super().__init__(f'{task!r} is not a task id like T1, C1, or R1')


class GitMissingError(TaskStateError):
    def __init__(self) -> None:
        super().__init__('git is not on PATH; ownership cannot be checked')


class GitUnavailableError(TaskStateError):
    def __init__(self, detail: str) -> None:
        super().__init__(f'git could not list the commit changes: {detail}')


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path
    slug: str

    @property
    def ticket_dir(self) -> Path:
        return self.root / '.mightymodels' / self.slug

    @property
    def work_unit(self) -> Path:
        return self.ticket_dir / 'work-unit.json'

    @property
    def transitions(self) -> Path:
        return self.ticket_dir / 'transitions.jsonl'

    @property
    def contract(self) -> Path:
        return self.ticket_dir / 'verification' / 'contract.json'

    @property
    def receipts(self) -> Path:
        return self.ticket_dir / 'verification' / 'receipts.jsonl'


@dataclass(slots=True)
class Task:
    status: Status = Status.PENDING
    owned: list[str] = field(default_factory=list)
    base: str | None = None
    commit: str | None = None
    attempts: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Transition:
    task: str
    before: Status
    after: Status
    reasons: list[str]
    head: str | None


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


def resolve_head(root: Path) -> str | None:
    directory = git_dir(root)
    head = read_text(directory / 'HEAD')
    if head is None or not head.startswith('ref:'):
        return head
    ref = head.removeprefix('ref:').strip()
    shared = common_dir(directory)
    return read_text(directory / ref) or read_text(shared / ref) or packed_ref(shared, ref)


def load_unit(paths: Paths) -> dict[str, object]:
    if not paths.work_unit.is_file():
        raise NotStagedError(paths.work_unit)
    return json.loads(paths.work_unit.read_text(encoding='utf-8'))


def tasks_of(unit: dict[str, object]) -> dict[str, Task]:
    progress = unit.get('progress')
    raw = progress.get('tasks', {}) if isinstance(progress, dict) else {}
    return {
        task_id: Task(**{**entry, 'status': Status(entry['status'])})
        for task_id, entry in raw.items()
    }


def task_record(task: Task) -> dict[str, object]:
    return {
        'status': str(task.status),
        'owned': task.owned,
        'base': task.base,
        'commit': task.commit,
        'attempts': task.attempts,
        'reasons': task.reasons,
    }


def persist(paths: Paths, tasks: dict[str, Task], transition: Transition) -> None:
    unit = load_unit(paths)
    records = {task_id: task_record(task) for task_id, task in tasks.items()}
    unit['progress'] = {'tasks': records, 'updated_at': now()}
    unit['status'] = 'in-progress'
    temporary = paths.work_unit.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(unit, indent=2) + '\n', encoding='utf-8')
    temporary.replace(paths.work_unit)
    entry = {
        'schema': SCHEMA_VERSION,
        'task': transition.task,
        'from': str(transition.before),
        'to': str(transition.after),
        'reasons': transition.reasons,
        'head': transition.head,
        'at': now(),
    }
    with paths.transitions.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry) + '\n')


def checked_task_id(task: str) -> str:
    if not TASK_ID.match(task):
        raise InvalidTaskError(task)
    return task


def safe_revision(revision: str) -> str:
    if not SAFE_REVISION.match(revision):
        raise UnsafeRevisionError(revision)
    return revision


def require_transition(task_id: str, task: Task, target: Status) -> None:
    if target not in ALLOWED[task.status]:
        raise TransitionError(task_id, task.status, target)


def changed_files(root: Path, base: str, commit: str) -> set[str]:
    git = shutil.which('git')
    if git is None:
        raise GitMissingError
    revisions = f'{safe_revision(base)}..{safe_revision(commit)}'
    completed = subprocess.run(  # noqa: S603 - fixed git argv; both revisions are validated plain names
        [git, 'diff', '--name-only', revisions, '--'],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GitUnavailableError(completed.stderr.strip())
    return {line for line in completed.stdout.splitlines() if line}


def resolve_commit(root: Path, revision: str) -> str | None:
    revision = safe_revision(revision)
    git = shutil.which('git')
    if git is None:
        raise GitMissingError
    result = subprocess.run(
        [git, 'rev-parse', '--verify', '--quiet', f'{revision}^{{commit}}'],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def commit_problems(paths: Paths, task: Task, commit: str) -> list[str]:
    if commit != resolve_head(paths.root):
        return ['the reported commit must resolve to the current HEAD']
    if task.base is None or resolve_commit(paths.root, task.base) is None:
        return ['the task has no valid base commit']
    result = subprocess.run(
        [shutil.which('git') or 'git', 'merge-base', '--is-ancestor', task.base, commit],
        cwd=paths.root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode > 1:
        raise GitUnavailableError(result.stderr.strip())
    return ['the task base is not an ancestor of the reported commit'] if result.returncode else []


def brief_problems(paths: Paths, evidence: Evidence) -> list[str]:
    if evidence.brief is None:
        return []
    if not evidence.brief.is_file():
        return ['the task brief is missing']
    _, separator, done = evidence.brief.read_text(encoding='utf-8').partition('## DONE')
    match = re.search(r'^\s*commit:\s*([0-9a-fA-F]{7,64})\s*$', done, re.MULTILINE)
    if not separator or match is None or resolve_commit(paths.root, match[1]) != evidence.commit:
        return ['the DONE brief must name the reported HEAD commit']
    return []


def latest_receipts(paths: Paths) -> dict[str, dict[str, object]]:
    if not paths.receipts.is_file():
        return {}
    lines = paths.receipts.read_text(encoding='utf-8').splitlines()
    return {str(entry['id']): entry for entry in map(json.loads, filter(None, lines))}


def contract_ids(paths: Paths, prefix: str) -> list[str]:
    if not paths.contract.is_file():
        return []
    commands = json.loads(paths.contract.read_text(encoding='utf-8'))['commands']
    return sorted(command for command in commands if command.startswith(prefix))


def criteria_in_brief(brief: Path | None) -> list[str]:
    if brief is None or not brief.is_file():
        return []
    asked = brief.read_text(encoding='utf-8').split('## DONE', 1)[0]
    return ASKED_CRITERION.findall(asked)


@dataclass(frozen=True, slots=True)
class Evidence:
    task_id: str
    commit: str
    brief: Path | None
    assertions: dict[str, str]


def receipt_problems(paths: Paths, prefix: str, head: str | None) -> list[str]:
    receipts = latest_receipts(paths)
    problems = []
    for command_id in contract_ids(paths, prefix):
        receipt = receipts.get(command_id)
        if receipt is None or receipt.get('head') != head:
            problems.append(f'{command_id} has no receipt at the current HEAD')
        elif receipt.get('outcome') != 'pass':
            problems.append(f'{command_id} {receipt.get("outcome")} at HEAD')

    return problems


def criteria_problems(paths: Paths, evidence: Evidence) -> list[str]:
    commands = contract_ids(paths, f'{evidence.task_id}.')
    proven = {command.split('.', 1)[1] for command in commands} | set(evidence.assertions)
    missing = [
        criterion for criterion in criteria_in_brief(evidence.brief) if criterion not in proven
    ]
    problems = [
        f'{criterion} has neither a contract command nor a citation' for criterion in missing
    ]
    if not commands and not evidence.assertions:
        problems.append('no contract command and no cited assertion proves this task')
    return problems


def ownership_problems(paths: Paths, task: Task, commit: str) -> list[str]:
    if task.base is None:
        return ['the task was never started with a base commit']
    outside = sorted(changed_files(paths.root, task.base, commit) - set(task.owned))
    return [f'changed outside the owned set: {path}' for path in outside]


def evidence_from(options: argparse.Namespace, paths: Paths) -> Evidence:
    assertions = dict(item.split('=', 1) for item in options.assertion or [])
    task_id = checked_task_id(options.task)
    brief = options.brief
    if brief is None and task_id.startswith(PLAN_TASK):
        brief = paths.ticket_dir / 'briefs' / f'task-{int(task_id[1:]):02d}.md'
    commit = resolve_commit(paths.root, options.commit)
    return Evidence(task_id, commit or options.commit, brief, assertions)


def verification_problems(paths: Paths, task: Task, evidence: Evidence) -> list[str]:
    problems = commit_problems(paths, task, evidence.commit)
    if problems:
        return problems
    return [
        *receipt_problems(paths, f'{evidence.task_id}.', resolve_head(paths.root)),
        *brief_problems(paths, evidence),
        *criteria_problems(paths, evidence),
        *ownership_problems(paths, task, evidence.commit),
    ]


def task_number(task_id: str) -> int:
    return int(task_id[1:])


def task_order(item: tuple[str, Task]) -> tuple[bool, int]:
    return item[0][0] != PLAN_TASK, task_number(item[0])


def planned_tasks(paths: Paths, tasks: dict[str, Task]) -> set[str]:
    from_contract = {command.split('.', 1)[0] for command in contract_ids(paths, PLAN_TASK)}
    started = {task_id for task_id in tasks if task_id.startswith(PLAN_TASK)}
    return {task_id for task_id in from_contract | started if TASK_ID.match(task_id)}


def readiness_problems(paths: Paths, tasks: dict[str, Task]) -> list[str]:
    planned = planned_tasks(paths, tasks)
    problems = [] if planned else ['no plan task has been started']
    for task_id in sorted(planned, key=task_number):
        status = tasks[task_id].status if task_id in tasks else None
        if status is None:
            problems.append(f'{task_id} has contract commands but was never started')
        elif status is not Status.VERIFIED:
            problems.append(f'{task_id} is {status}, not verified')
    problems.extend(
        f'{task_id} is {task.status}: {"; ".join(task.reasons)}'
        for task_id, task in sorted(tasks.items(), key=task_order)
        if task_id not in planned and task.status in STUCK
    )
    return problems


def run_start(options: argparse.Namespace, paths: Paths) -> tuple[str, bool]:
    task_id = checked_task_id(options.task)
    tasks = tasks_of(load_unit(paths))
    task = tasks.setdefault(task_id, Task())
    worker = Worker(options.by)
    limit = ARCHITECT_LIMIT + int(options.expanded_envelope)
    if worker is Worker.ARCHITECT and task.attempts.get(worker, 0) >= limit:
        raise ArchitectSpentError(task_id)
    require_transition(task_id, task, Status.IN_PROGRESS)
    head = resolve_head(paths.root)
    before = task.status
    task.status, task.base, task.commit, task.reasons = Status.IN_PROGRESS, head, None, []
    task.owned = sorted(set(options.owned))
    task.attempts[worker] = task.attempts.get(worker, 0) + 1
    persist(paths, tasks, Transition(task_id, before, task.status, [f'by {worker}'], head))
    return f'{task_id} in-progress by {worker} from {(head or "unknown")[:12]}\n', True


def run_verify(options: argparse.Namespace, paths: Paths) -> tuple[str, bool]:
    task_id = checked_task_id(options.task)
    tasks = tasks_of(load_unit(paths))
    task = tasks.setdefault(task_id, Task())
    require_transition(task_id, task, Status.VERIFIED)
    head = resolve_head(paths.root)
    evidence = evidence_from(options, paths)
    problems = verification_problems(paths, task, evidence)
    before = task.status
    task.status = Status.BLOCKED if problems else Status.VERIFIED
    task.commit, task.reasons = evidence.commit, problems
    persist(paths, tasks, Transition(task_id, before, task.status, problems, head))
    lines = ''.join(f'  - {problem}\n' for problem in problems)
    return f'{task_id} {task.status}\n{lines}', not problems


def run_mark(options: argparse.Namespace, paths: Paths) -> tuple[str, bool]:
    task_id = checked_task_id(options.task)
    tasks = tasks_of(load_unit(paths))
    task = tasks.setdefault(task_id, Task())
    target = Status(options.to)
    require_transition(task_id, task, target)
    before = task.status
    task.status, task.reasons = target, [options.reason]
    persist(paths, tasks, Transition(task_id, before, target, [options.reason], None))
    return f'{task_id} {target}: {options.reason}\n', True


def run_show(_options: argparse.Namespace, paths: Paths) -> tuple[str, bool]:
    tasks = tasks_of(load_unit(paths))
    rows = [
        f'{task_id}\t{task.status}\tattempts {task.attempts}\t{"; ".join(task.reasons)}\n'
        for task_id, task in sorted(tasks.items(), key=task_order)
    ]
    return ''.join(rows) or 'no tasks started\n', True


def run_ready(_options: argparse.Namespace, paths: Paths) -> tuple[str, bool]:
    head = resolve_head(paths.root)
    problems = [
        *readiness_problems(paths, tasks_of(load_unit(paths))),
        *receipt_problems(paths, '', head),
    ]
    if not problems:
        return f'ready at {(head or "unknown")[:12]}\n', True
    return 'not ready\n' + ''.join(f'  - {problem}\n' for problem in problems), False


HANDLERS: dict[Command, Callable[[argparse.Namespace, Paths], tuple[str, bool]]] = {
    Command.START: run_start,
    Command.VERIFY: run_verify,
    Command.MARK: run_mark,
    Command.SHOW: run_show,
    Command.READY: run_ready,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='task_state.py', description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest='command', required=True)
    start = commands.add_parser(Command.START, help='begin an attempt on a task')
    start.add_argument('--by', required=True, choices=[worker.value for worker in Worker])
    start.add_argument('--owned', required=True, nargs='+')
    start.add_argument('--expanded-envelope', action='store_true')
    verify = commands.add_parser(Command.VERIFY, help='gate a task on its evidence')
    verify.add_argument('--commit', required=True)
    verify.add_argument('--brief', type=Path)
    verify.add_argument('--assertion', action='append')
    mark = commands.add_parser(Command.MARK, help='record a failed or blocked attempt')
    mark.add_argument('--to', required=True, choices=[status.value for status in MARKABLE])
    mark.add_argument('--reason', required=True)
    show = commands.add_parser(Command.SHOW, help='list task states')
    ready = commands.add_parser(Command.READY, help='gate a push on the whole ticket')
    for sub in (start, verify, mark, show, ready):
        sub.add_argument('--slug', required=True)
    for sub in (start, verify, mark):
        sub.add_argument('--task', required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        paths = Paths(root=repository_root(Path.cwd()), slug=options.slug)
        output, advanced = HANDLERS[Command(options.command)](options, paths)
    except TaskStateError as error:
        sys.stderr.write(f'error: {error}\n')
        return EXIT_REJECTED
    sys.stdout.write(output)
    return 0 if advanced else EXIT_BLOCKED


if __name__ == '__main__':
    raise SystemExit(main())
