"""The task service: starts, verifies and marks tasks, records failed fixes, shows and readies them.

It takes values and returns values. The caller asks git and reads the brief, passes HEAD, the git
facts and the brief text in, and renders the records and problems this service returns; the service
never touches git or the filesystem. Verify runs as two calls so the caller can ask git between
them: `prepare_verification` reads the task, and `verify` takes the git facts, reads the task again
and refuses when its status, base or owned set moved since.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact, redact_within
from mightymodels_core.tasks.errors import TaskMovedError, TransitionError, UnknownTaskError
from mightymodels_core.tasks.gates import (
    Evidence,
    VerificationGate,
    get_readiness_problems,
    get_receipt_problems,
    is_plan_task,
)
from mightymodels_core.tasks.policy import (
    IMPLEMENTATION_MODES,
    FixPolicy,
    StartPolicy,
    TaskOptions,
    TransitionPolicy,
)
from mightymodels_core.tasks.records import Attempt, FailedFix, Transition

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.contract.repository import ContractRepository
    from mightymodels_core.primitives import Clock, RedactedText, Slug, TaskId
    from mightymodels_core.schemas.tasks import ArchitectMode, TaskStatus, Worker
    from mightymodels_core.tasks.gates import Brief, GitFacts
    from mightymodels_core.tasks.records import AttemptCounts, TaskRecord
    from mightymodels_core.tasks.repository import AttemptRepository, TaskRepository
    from mightymodels_core.tickets.repository import TicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class StartRequest:
    task_key: TaskId
    worker: Worker
    mode: ArchitectMode | None
    owned: tuple[str, ...]
    acceptance_count: int
    head: str | None
    too_large_approved: bool = False


@dataclass(slots=True, kw_only=True, frozen=True)
class VerifyRequest:
    seen: TaskRecord
    commit: str
    assertions: Mapping[str, str]
    git: GitFacts
    brief: Brief | None


@dataclass(slots=True, kw_only=True, frozen=True)
class MarkRequest:
    task_key: TaskId
    to: TaskStatus
    reason: str


@dataclass(slots=True, kw_only=True, frozen=True)
class FixRecorded:
    hypothesis: RedactedText
    number: int
    remaining: int


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskListing:
    records: list[TaskRecord]
    attempts: AttemptCounts


@dataclass(slots=True, kw_only=True, frozen=True)
class Readiness:
    records: list[TaskRecord]
    problems: list[str]


def status_of(task: TaskRecord | None) -> TaskStatus:
    return 'pending' if task is None else task.status


def get_moved_fields(seen: TaskRecord, current: TaskRecord) -> list[str]:
    moved = {
        'status': seen.status != current.status,
        'base': seen.base != current.base,
        'owned set': seen.owned != current.owned,
    }
    return [field_name for field_name, changed in moved.items() if changed]


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskService:
    tickets: TicketRepository
    tasks: TaskRepository
    attempts: AttemptRepository
    contracts: ContractRepository
    clock: Clock
    options: TaskOptions = field(default_factory=TaskOptions)

    def start(self, slug: Slug, request: StartRequest) -> TaskRecord:
        ticket_id = self.tickets.unclosed_ticket(slug).id
        task_key = request.task_key
        policy = StartPolicy(
            task_key=task_key,
            before=status_of(self.tasks.task(ticket_id, task_key)),
            worker=request.worker,
            mode=request.mode,
            attempts=self.attempts.attempts_by_worker(ticket_id).get(task_key, {}),
            implementation_spent=self.attempts.attempts_in_modes(
                ticket_id, task_key, IMPLEMENTATION_MODES
            ),
            acceptance_count=request.acceptance_count,
            owned_count=len(set(request.owned)),
            too_large_approved=request.too_large_approved,
            options=self.options,
        )
        if problem := policy.get_start_problem():
            raise problem

        transition = Transition(
            task_key=task_key,
            before=policy.before,
            after='in-progress',
            reasons=tuple(map(redact, policy.reasons)),
            head=request.head,
            at=self.clock.now(),
        )
        attempt = Attempt(
            worker=request.worker,
            mode=policy.architect_mode,
            owned=tuple(sorted(set(request.owned))),
        )
        self.tickets.mark_in_progress(slug)
        self.tasks.record_start(ticket_id, transition, attempt)
        return self.task_held(ticket_id, task_key)

    def prepare_verification(self, slug: Slug, task_key: TaskId) -> TaskRecord:
        ticket_id = self.tickets.unclosed_ticket(slug).id
        task = self.tasks.task(ticket_id, task_key)
        if task is None:
            raise TransitionError(task_key=task_key, current='pending', target='verified')

        self.check_verifiable(task)
        return task

    def check_verifiable(self, task: TaskRecord) -> None:
        policy = TransitionPolicy(
            task_key=task.key, before=task.status, after='verified', options=self.options
        )
        if problem := policy.get_transition_problem():
            raise problem

    def verify(self, slug: Slug, request: VerifyRequest) -> TaskRecord:
        ticket_id = self.tickets.unclosed_ticket(slug).id
        task_key = request.seen.key
        current = self.task_held(ticket_id, task_key)
        if moved := get_moved_fields(request.seen, current):
            raise TaskMovedError(task_key=task_key, changed=moved)

        self.check_verifiable(current)
        gate = VerificationGate(
            task=current, evidence=self.evidence_for(ticket_id, current, request), git=request.git
        )
        problems = gate.get_verification_problems()
        transition = Transition(
            task_key=task_key,
            before=current.status,
            after='blocked' if problems else 'verified',
            reasons=tuple(map(redact, problems)),
            head=request.git.head,
            at=self.clock.now(),
        )
        self.tickets.mark_in_progress(slug)
        self.tasks.record_verification(ticket_id, transition, request.commit)
        return self.task_held(ticket_id, task_key)

    def evidence_for(self, ticket_id: int, task: TaskRecord, request: VerifyRequest) -> Evidence:
        own = [
            command
            for command in self.contracts.commands(ticket_id)
            if command.task_key == task.key
        ]
        return Evidence(
            commit=request.commit,
            brief=request.brief if is_plan_task(task.key) else None,
            assertions=request.assertions,
            commands=own,
            receipts=self.contracts.latest_receipts(ticket_id),
        )

    def mark(self, slug: Slug, request: MarkRequest) -> TaskRecord:
        ticket_id = self.tickets.unclosed_ticket(slug).id
        task_key = request.task_key
        before = status_of(self.tasks.task(ticket_id, task_key))
        policy = TransitionPolicy(
            task_key=task_key, before=before, after=request.to, options=self.options
        )
        if problem := policy.get_transition_problem():
            raise problem

        transition = Transition(
            task_key=task_key,
            before=before,
            after=request.to,
            reasons=(redact(request.reason),),
            head=None,
            at=self.clock.now(),
        )
        self.tickets.mark_in_progress(slug)
        self.tasks.record_mark(ticket_id, transition)
        return self.task_held(ticket_id, task_key)

    def record_failed_fix(self, slug: Slug, task_key: TaskId, hypothesis: str) -> FixRecorded:
        redacted = redact_within(hypothesis, 'hypothesis', self.options.hypothesis_limit)
        ticket_id = self.tickets.unclosed_ticket(slug).id
        tried = self.attempts.failed_fixes(ticket_id, task_key)
        policy = FixPolicy(
            task_key=task_key,
            before=status_of(self.tasks.task(ticket_id, task_key)),
            tried=tried,
            options=self.options,
        )
        if problem := policy.get_fix_problem():
            raise problem

        fix = FailedFix(task_key=task_key, hypothesis=redacted, at=self.clock.now())
        self.attempts.record_failed_fix(ticket_id, fix)
        number = len(tried) + 1
        return FixRecorded(
            hypothesis=redacted, number=number, remaining=self.options.failed_fix_limit - number
        )

    def show(self, slug: Slug) -> TaskListing:
        ticket_id = self.tickets.staged_ticket(slug).id
        return TaskListing(
            records=self.tasks.tasks(ticket_id),
            attempts=self.attempts.attempts_by_worker(ticket_id),
        )

    def ready(self, slug: Slug, head: str | None) -> Readiness:
        ticket_id = self.tickets.staged_ticket(slug).id
        records = self.tasks.tasks(ticket_id)
        superseded = {record.key for record in records if record.status == 'superseded'}
        live = [
            command
            for command in self.contracts.commands(ticket_id)
            if command.task_key not in superseded
        ]
        receipts = self.contracts.latest_receipts(ticket_id)
        problems = [
            *get_readiness_problems(records),
            *get_receipt_problems(live, receipts, head),
        ]
        return Readiness(records=records, problems=problems)

    def task_held(self, ticket_id: int, task_key: TaskId) -> TaskRecord:
        held = self.tasks.task(ticket_id, task_key)
        if held is None:
            raise UnknownTaskError(ticket_id=ticket_id, task_key=task_key)

        return held
