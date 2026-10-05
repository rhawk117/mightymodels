"""The `task` tool's service: per-task state, gated, and durable before anything advances.

Every transition is checked and stored with its transition row in one transaction. A task
reaches verified only when every contract command for it passed at the current HEAD, every
other acceptance criterion carries a citation, and the commit touched only the files the
task owns. Plan tasks are T1, T2, ...; fixes for failing CI checks are C1, C2, ...; review
remediation of finding Fn is Rn. `ready` is the gate before any push.

The ladder is the skills': an engineer attempt, one architect implementation attempt, one
more in systemic-refactor mode after an approved scope expansion, which may take over a task
that is still in progress, and diagnose-replan passes that never count against the limit. A
replanned task closes as superseded, which `ready` treats as closed.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from sqlalchemy import select

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.db.tables import (
    AttemptRow,
    CommandRow,
    ReceiptRow,
    TaskRow,
    TicketRow,
    TransitionRow,
)
from mightymodels_plugin.errors import StateError
from mightymodels_plugin.models.contract import Outcome
from mightymodels_plugin.models.slug import Slug
from mightymodels_plugin.models.task import (
    PLAN_TASK,
    ArchitectMode,
    Implementer,
    Status,
    TaskMark,
    TaskRecord,
    TaskStart,
    TaskVerification,
    TaskView,
)
from mightymodels_plugin.models.ticket import TicketStatus
from mightymodels_plugin.services.clock import now
from mightymodels_plugin.services.contract import commands_of, latest_receipts
from mightymodels_plugin.services.git import (
    changed_files,
    is_ancestor,
    resolve_commit,
    resolve_head,
)
from mightymodels_plugin.services.layout import task_brief
from mightymodels_plugin.services.ticket import staged_row

ARCHITECT_LIMIT = 1
SHORT_SHA = 12
DONE_HEADING = '## DONE'
ASKED_CRITERION = re.compile(r'^\s*-\s*(AC-\d+)\s*:', re.MULTILINE)
DONE_COMMIT = re.compile(r'^\s*commit:\s*([0-9a-fA-F]{7,64})\s*$', re.MULTILINE)

TERMINAL = frozenset[Status]()
ALLOWED: Mapping[Status, frozenset[Status]] = MappingProxyType(
    {
        Status.PENDING: frozenset({Status.IN_PROGRESS}),
        Status.IN_PROGRESS: frozenset(
            {Status.VERIFIED, Status.FAILED, Status.BLOCKED, Status.SUPERSEDED}
        ),
        Status.FAILED: frozenset({Status.IN_PROGRESS, Status.SUPERSEDED}),
        Status.BLOCKED: frozenset({Status.IN_PROGRESS, Status.SUPERSEDED}),
        Status.VERIFIED: TERMINAL,
        Status.SUPERSEDED: TERMINAL,
    }
)
STUCK = frozenset({Status.FAILED, Status.BLOCKED})
CLOSED = frozenset({Status.VERIFIED, Status.SUPERSEDED})
IMPLEMENTATION_MODES = frozenset(
    {ArchitectMode.RECOVERY_IMPLEMENTATION, ArchitectMode.SYSTEMIC_REFACTOR}
)


class TransitionError(StateError):
    def __init__(self, task_id: str, current: Status, target: Status) -> None:
        super().__init__(f'{task_id} cannot move from {current} to {target}')
        self.task_id = task_id
        self.current = current
        self.target = target


class ArchitectSpentError(StateError):
    def __init__(self, task_id: str) -> None:
        super().__init__(
            f'{task_id} already had its architect recovery; route it to whats-broken, start it '
            f'in {ArchitectMode.SYSTEMIC_REFACTOR} mode after the user approves a scope '
            f'expansion, or in {ArchitectMode.DIAGNOSE_REPLAN} mode for a revised contract'
        )
        self.task_id = task_id


class ModeNeedsArchitectError(StateError):
    def __init__(self, mode: ArchitectMode) -> None:
        super().__init__(f'{mode} is an architect mode; start the task by architect to use it')
        self.mode = mode


@dataclass(slots=True, kw_only=True, frozen=True)
class Transition:
    task_id: str
    before: Status
    after: Status
    reasons: Sequence[str]
    head: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Evidence:
    commit: str
    brief: Path | None
    assertions: Mapping[str, str]
    commands: Sequence[CommandRow]
    receipts: Mapping[str, ReceiptRow]


def task_number(task_id: str) -> int:
    return int(task_id[1:])


def is_plan_task(task_id: str) -> bool:
    return task_id.startswith(PLAN_TASK)


def task_order(record: TaskRecord) -> tuple[bool, int]:
    return not is_plan_task(record.id), task_number(record.id)


def row_of(checkout: Checkout, slug: Slug, task_id: str) -> TaskRow | None:
    return checkout.session.get(TaskRow, (slug.root, task_id))


def status_of(row: TaskRow | None) -> Status:
    return Status.PENDING if row is None else Status(row.status)


def attempt_counts(checkout: Checkout, slug: Slug) -> dict[str, dict[str, int]]:
    query = select(AttemptRow).where(AttemptRow.slug == slug.root).order_by(AttemptRow.id)
    counts: dict[str, dict[str, int]] = {}
    for attempt in checkout.session.scalars(query):
        by_worker = counts.setdefault(attempt.task_id, {})
        by_worker[attempt.worker] = by_worker.get(attempt.worker, 0) + 1
    return counts


def implementation_attempts(checkout: Checkout, slug: Slug, task_id: str) -> int:
    query = select(AttemptRow).where(
        AttemptRow.slug == slug.root,
        AttemptRow.task_id == task_id,
        AttemptRow.mode.in_(sorted(IMPLEMENTATION_MODES)),
    )
    return len(checkout.session.scalars(query).all())


def record_of(row: TaskRow, attempts: dict[str, int]) -> TaskRecord:
    return TaskRecord(
        id=row.task_id,
        status=Status(row.status),
        owned=tuple(row.owned),
        base=row.base,
        commit=row.commit,
        attempts=attempts,
        reasons=tuple(row.reasons),
    )


def records_of(checkout: Checkout, slug: Slug) -> dict[str, TaskRecord]:
    attempts = attempt_counts(checkout, slug)
    query = select(TaskRow).where(TaskRow.slug == slug.root)
    started = [
        record_of(row, attempts.get(row.task_id, {})) for row in checkout.session.scalars(query)
    ]
    known = {record.id for record in started}
    planned = {
        command.task_id
        for command in commands_of(checkout, slug)
        if command.task_id is not None and is_plan_task(command.task_id)
    }
    pending = [TaskRecord(id=task_id, status=Status.PENDING) for task_id in planned - known]
    return {record.id: record for record in sorted([*started, *pending], key=task_order)}


def record_transition(checkout: Checkout, ticket: TicketRow, transition: Transition) -> None:
    ticket.status = TicketStatus.IN_PROGRESS
    checkout.session.add(
        TransitionRow(
            slug=ticket.slug,
            task_id=transition.task_id,
            before=transition.before,
            after=transition.after,
            reasons=list(transition.reasons),
            head=transition.head,
            at=now(),
        )
    )


def architect_mode(change: TaskStart) -> ArchitectMode | None:
    if change.by is Implementer.ARCHITECT:
        return change.mode or ArchitectMode.RECOVERY_IMPLEMENTATION
    if change.mode is not None:
        raise ModeNeedsArchitectError(change.mode)
    return None


def start_error(task_id: str, before: Status, mode: ArchitectMode | None) -> StateError | None:
    expanded = mode is ArchitectMode.SYSTEMIC_REFACTOR
    if Status.IN_PROGRESS in ALLOWED[before] or (expanded and before is Status.IN_PROGRESS):
        return None
    return TransitionError(task_id, before, Status.IN_PROGRESS)


def start(checkout: Checkout, slug: Slug, *, task_id: str, change: TaskStart) -> TaskView:
    ticket = staged_row(checkout, slug)
    mode = architect_mode(change)
    limit = ARCHITECT_LIMIT + int(mode is ArchitectMode.SYSTEMIC_REFACTOR)
    spent = implementation_attempts(checkout, slug, task_id)
    if mode in IMPLEMENTATION_MODES and spent >= limit:
        raise ArchitectSpentError(task_id)
    before = status_of(row_of(checkout, slug, task_id))
    error = start_error(task_id, before, mode)
    if error is not None:
        raise error
    head = resolve_head(checkout.root)
    checkout.session.merge(
        TaskRow(
            slug=slug.root,
            task_id=task_id,
            status=Status.IN_PROGRESS,
            owned=sorted(set(change.owned)),
            base=head,
            commit=None,
            reasons=[],
            updated_at=now(),
        )
    )
    checkout.session.add(
        AttemptRow(slug=slug.root, task_id=task_id, worker=change.by, mode=mode, at=now())
    )
    reasons = [f'by {change.by}', *([] if mode is None else [f'in {mode} mode'])]
    record_transition(
        checkout,
        ticket,
        Transition(
            task_id=task_id, before=before, after=Status.IN_PROGRESS, reasons=reasons, head=head
        ),
    )
    text = f'{task_id} in-progress by {change.by} from {(head or "unknown")[:SHORT_SHA]}\n'
    return TaskView(text=text, advanced=True, tasks=(records_of(checkout, slug)[task_id],))


def commit_problems(root: Path, base: str | None, commit: str) -> list[str]:
    if commit != resolve_head(root):
        return ['the reported commit must resolve to the current HEAD']
    if base is None or resolve_commit(root, base) is None:
        return ['the task has no valid base commit']
    if not is_ancestor(root, base, commit):
        return ['the task base is not an ancestor of the reported commit']
    return []


def brief_problems(root: Path, evidence: Evidence) -> list[str]:
    if evidence.brief is None:
        return []
    if not evidence.brief.is_file():
        return ['the task brief is missing']
    _, separator, done = evidence.brief.read_text(encoding='utf-8').partition(DONE_HEADING)
    named = DONE_COMMIT.search(done)
    if not separator or named is None or resolve_commit(root, named[1]) != evidence.commit:
        return ['the DONE brief must name the reported HEAD commit']
    return []


def receipt_problem(command_id: str, receipt: ReceiptRow | None, head: str | None) -> str | None:
    if receipt is None or receipt.head != head:
        return f'{command_id} has no receipt at the current HEAD'
    if receipt.outcome != Outcome.PASSED:
        return f'{command_id} {receipt.outcome} at HEAD'
    return None


def receipt_problems(
    commands: Sequence[CommandRow], receipts: Mapping[str, ReceiptRow], head: str | None
) -> list[str]:
    problems = (
        receipt_problem(command.command_id, receipts.get(command.command_id), head)
        for command in commands
    )
    return [problem for problem in problems if problem is not None]


def criteria_in_brief(brief: Path | None) -> list[str]:
    if brief is None or not brief.is_file():
        return []
    asked = brief.read_text(encoding='utf-8').split(DONE_HEADING, 1)[0]
    return [found[1] for found in ASKED_CRITERION.finditer(asked)]


def criteria_problems(evidence: Evidence) -> list[str]:
    by_command = {command.command_id.split('.', 1)[1] for command in evidence.commands}
    proven = by_command | set(evidence.assertions)
    problems = [
        f'{criterion} has neither a contract command nor a citation'
        for criterion in criteria_in_brief(evidence.brief)
        if criterion not in proven
    ]
    if not evidence.commands and not evidence.assertions:
        problems.append('no contract command and no cited assertion proves this task')
    return problems


def ownership_problems(root: Path, row: TaskRow, *, base: str, commit: str) -> list[str]:
    outside = sorted(changed_files(root, base, commit) - set(row.owned))
    return [f'changed outside the owned set: {path}' for path in outside]


def verification_problems(root: Path, row: TaskRow, evidence: Evidence) -> list[str]:
    base = row.base
    problems = commit_problems(root, base, evidence.commit)
    if problems or base is None:
        return problems
    return [
        *receipt_problems(evidence.commands, evidence.receipts, resolve_head(root)),
        *brief_problems(root, evidence),
        *criteria_problems(evidence),
        *ownership_problems(root, row, base=base, commit=evidence.commit),
    ]


def evidence_for(
    checkout: Checkout, slug: Slug, *, row: TaskRow, change: TaskVerification
) -> Evidence:
    planned = is_plan_task(row.task_id)
    commands = [
        command for command in commands_of(checkout, slug) if command.task_id == row.task_id
    ]
    return Evidence(
        commit=resolve_commit(checkout.root, change.commit) or change.commit,
        brief=task_brief(checkout.root, slug, task_number(row.task_id)) if planned else None,
        assertions=change.assertions,
        commands=commands,
        receipts=latest_receipts(checkout, slug),
    )


def verify(checkout: Checkout, slug: Slug, *, task_id: str, change: TaskVerification) -> TaskView:
    ticket = staged_row(checkout, slug)
    row = row_of(checkout, slug, task_id)
    before = status_of(row)
    if row is None or Status.VERIFIED not in ALLOWED[before]:
        raise TransitionError(task_id, before, Status.VERIFIED)
    head = resolve_head(checkout.root)
    evidence = evidence_for(checkout, slug, row=row, change=change)
    problems = verification_problems(checkout.root, row, evidence)
    after = Status.BLOCKED if problems else Status.VERIFIED
    row.status, row.commit, row.reasons, row.updated_at = after, evidence.commit, problems, now()
    record_transition(
        checkout,
        ticket,
        Transition(task_id=task_id, before=before, after=after, reasons=problems, head=head),
    )
    lines = ''.join(f'  - {problem}\n' for problem in problems)
    return TaskView(
        text=f'{task_id} {after}\n{lines}',
        advanced=not problems,
        tasks=(records_of(checkout, slug)[task_id],),
    )


def mark(checkout: Checkout, slug: Slug, *, task_id: str, change: TaskMark) -> TaskView:
    ticket = staged_row(checkout, slug)
    row = row_of(checkout, slug, task_id)
    before = status_of(row)
    if row is None or change.to not in ALLOWED[before]:
        raise TransitionError(task_id, before, change.to)
    row.status, row.reasons, row.updated_at = change.to, [change.reason], now()
    record_transition(
        checkout,
        ticket,
        Transition(
            task_id=task_id, before=before, after=change.to, reasons=[change.reason], head=None
        ),
    )
    return TaskView(
        text=f'{task_id} {change.to}: {change.reason}\n',
        advanced=True,
        tasks=(records_of(checkout, slug)[task_id],),
    )


def show(checkout: Checkout, slug: Slug) -> TaskView:
    staged_row(checkout, slug)
    records = tuple(records_of(checkout, slug).values())
    rows = [
        f'{record.id}\t{record.status}\tattempts {record.attempts}\t{"; ".join(record.reasons)}\n'
        for record in records
    ]
    return TaskView(text=''.join(rows) or 'no tasks started\n', advanced=True, tasks=records)


def plan_task_problem(record: TaskRecord) -> str | None:
    if record.status is Status.PENDING:
        return f'{record.id} has contract commands but was never started'
    if record.status in CLOSED:
        return None
    return f'{record.id} is {record.status}, not verified'


def readiness_problems(records: Sequence[TaskRecord]) -> list[str]:
    planned = [record for record in records if is_plan_task(record.id)]
    unproven = (plan_task_problem(record) for record in planned)
    return [
        *([] if planned else ['no plan task has been started']),
        *(problem for problem in unproven if problem is not None),
        *(
            f'{record.id} is {record.status}: {"; ".join(record.reasons)}'
            for record in records
            if not is_plan_task(record.id) and record.status in STUCK
        ),
    ]


def ready(checkout: Checkout, slug: Slug) -> TaskView:
    staged_row(checkout, slug)
    head = resolve_head(checkout.root)
    records = tuple(records_of(checkout, slug).values())
    superseded = {record.id for record in records if record.status is Status.SUPERSEDED}
    live = [command for command in commands_of(checkout, slug) if command.task_id not in superseded]
    problems = [
        *readiness_problems(records),
        *receipt_problems(live, latest_receipts(checkout, slug), head),
    ]
    if not problems:
        text = f'ready at {(head or "unknown")[:SHORT_SHA]}\n'
        return TaskView(text=text, advanced=True, tasks=records)
    lines = ''.join(f'  - {problem}\n' for problem in problems)
    return TaskView(text=f'not ready\n{lines}', advanced=False, tasks=records)
