"""The task service: starts, verifies and marks tasks, records failed fixes.

It takes values and returns values. The caller asks git, passes HEAD and the git facts in, and
renders the records this service returns; the service never touches git or the filesystem. Verify
runs as two calls so the caller can ask git between them: `prepare_verification` reads the task,
and `verify` takes the git facts, reads the task again and refuses when its status, base or owned
set moved since. The verdict is the caller's; git facts never change it.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from mightymodels_core.primitives import redact, redact_within
from mightymodels_core.tasks.errors import (
    NotPlanTaskError,
    TaskMovedError,
    TransitionError,
    UndeclaredPlanTaskError,
    UnknownTaskError,
)
from mightymodels_core.tasks.gates import is_plan_task
from mightymodels_core.tasks.policy import (
    IMPLEMENTATION_MODES,
    FixPolicy,
    StartPolicy,
    TaskOptions,
    TransitionPolicy,
)
from mightymodels_core.tasks.records import Attempt, FailedFix, Transition
from mightymodels_core.tickets import open_ticket_of

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from mightymodels_core.primitives import Clock, RedactedText, Slug, TaskId
    from mightymodels_core.tasks.gates import GitFacts
    from mightymodels_core.tasks.records import TaskRecord
    from mightymodels_core.tasks.repository import AttemptRepository, TaskRepository
    from mightymodels_core.tickets.repository import TicketRepository
    from mightymodels_core.vocabulary.tasks import ArchitectMode, TaskStatus, Worker


@dataclass(slots=True, kw_only=True, frozen=True)
class StartRequest:
    task_key: TaskId
    worker: Worker
    mode: ArchitectMode | None
    owned: tuple[str, ...]
    acceptance_count: int
    head: str | None


type VerifyVerdict = Literal['verified', 'failed', 'blocked']


@dataclass(slots=True, kw_only=True, frozen=True)
class VerifyRequest:
    seen: TaskRecord
    commit: str
    verdict: VerifyVerdict
    reason: str | None
    git: GitFacts


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


def status_of(task: TaskRecord | None) -> TaskStatus:
    return 'pending' if task is None else task.status


def verification_transition(request: VerifyRequest, at: datetime) -> Transition:
    return Transition(
        task_key=request.seen.key,
        before=request.seen.status,
        after=request.verdict,
        reasons=tuple(map(redact, filter(None, [request.reason]))),
        head=request.git.head,
        at=at,
    )


def mark_transition(request: MarkRequest, before: TaskStatus, at: datetime) -> Transition:
    return Transition(
        task_key=request.task_key,
        before=before,
        after=request.to,
        reasons=(redact(request.reason),),
        head=None,
        at=at,
    )


def get_moved_fields(seen: TaskRecord, current: TaskRecord) -> list[str]:
    moved = {
        'status': seen.status != current.status,
        'base': seen.base != current.base,
        'owned set': seen.owned != current.owned,
    }
    return [field_name for field_name, changed in moved.items() if changed]


def start_transition(policy: StartPolicy, request: StartRequest, at: datetime) -> Transition:
    return Transition(
        task_key=request.task_key,
        before=policy.before,
        after='in-progress',
        reasons=tuple(map(redact, policy.reasons)),
        head=request.head,
        at=at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskService:
    tickets: TicketRepository
    tasks: TaskRepository
    attempts: AttemptRepository
    clock: Clock
    options: TaskOptions = field(default_factory=TaskOptions)

    def start(self, slug: Slug, request: StartRequest) -> TaskRecord:
        ticket = open_ticket_of(self.tickets, slug)
        ticket_id = ticket.id
        task_key = request.task_key
        if is_plan_task(task_key) and self.tasks.task(ticket_id, task_key) is None:
            raise UndeclaredPlanTaskError(task_key=task_key)

        policy = self.start_policy_for(ticket_id, request)
        if problem := policy.get_start_problem():
            raise problem

        attempt = Attempt(
            worker=request.worker,
            mode=policy.architect_mode,
            owned=tuple(sorted(set(request.owned))),
        )
        self.tickets.mark_in_progress(ticket)
        self.tasks.record_start(
            ticket_id, start_transition(policy, request, self.clock.now()), attempt
        )
        return self.task_held(ticket_id, request.task_key)

    def declare(self, slug: Slug, task_keys: Sequence[TaskId]) -> list[TaskRecord]:
        ticket = open_ticket_of(self.tickets, slug)
        ticket_id = ticket.id
        for task_key in task_keys:
            if not is_plan_task(task_key):
                raise NotPlanTaskError(task_key=task_key)

        self.tickets.mark_in_progress(ticket)
        self.tasks.declare(ticket_id, sorted(set(task_keys)), self.clock.now())
        return self.tasks.tasks(ticket_id)

    def prepare_verification(
        self, slug: Slug, task_key: TaskId, verdict: VerifyVerdict
    ) -> TaskRecord:
        ticket_id = open_ticket_of(self.tickets, slug).id
        task = self.tasks.task(ticket_id, task_key)
        if task is None:
            raise TransitionError(task_key=task_key, current='pending', target=verdict)

        self.check_verdict(task, verdict)
        return task

    def check_verdict(self, task: TaskRecord, verdict: VerifyVerdict) -> None:
        policy = TransitionPolicy(
            task_key=task.key, before=task.status, after=verdict, options=self.options
        )
        if problem := policy.get_transition_problem():
            raise problem

    def verify(self, slug: Slug, request: VerifyRequest) -> TaskRecord:
        ticket = open_ticket_of(self.tickets, slug)
        ticket_id = ticket.id
        task_key = request.seen.key
        current = self.task_held(ticket_id, task_key)
        if moved := get_moved_fields(request.seen, current):
            raise TaskMovedError(task_key=task_key, changed=moved)

        self.check_verdict(current, request.verdict)
        transition = verification_transition(request, self.clock.now())
        self.tickets.mark_in_progress(ticket)
        self.tasks.record_verification(ticket_id, transition, request.commit)
        return self.task_held(ticket_id, task_key)

    def mark(self, slug: Slug, request: MarkRequest) -> TaskRecord:
        ticket = open_ticket_of(self.tickets, slug)
        ticket_id = ticket.id
        task_key = request.task_key
        before = status_of(self.tasks.task(ticket_id, task_key))
        policy = TransitionPolicy(
            task_key=task_key, before=before, after=request.to, options=self.options
        )
        if problem := policy.get_transition_problem():
            raise problem

        transition = mark_transition(request, before, self.clock.now())
        self.tickets.mark_in_progress(ticket)
        self.tasks.record_mark(ticket_id, transition)
        return self.task_held(ticket_id, task_key)

    def record_failed_fix(self, slug: Slug, task_key: TaskId, hypothesis: str) -> FixRecorded:
        redacted = redact_within(hypothesis, 'hypothesis', self.options.hypothesis_limit)
        ticket_id = open_ticket_of(self.tickets, slug).id
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

    def start_policy_for(self, ticket_id: int, request: StartRequest) -> StartPolicy:
        task_key = request.task_key
        return StartPolicy(
            task_key=task_key,
            before=status_of(self.tasks.task(ticket_id, task_key)),
            worker=request.worker,
            mode=request.mode,
            attempts=self.attempts.attempts_by_worker(ticket_id).get(task_key, {}),
            implementation_spent=self.attempts.attempts_in_modes(
                ticket_id, task_key, IMPLEMENTATION_MODES
            ),
            options=self.options,
        )

    def task_held(self, ticket_id: int, task_key: TaskId) -> TaskRecord:
        held = self.tasks.task(ticket_id, task_key)
        if held is None:
            raise UnknownTaskError(ticket_id=ticket_id, task_key=task_key)

        return held
