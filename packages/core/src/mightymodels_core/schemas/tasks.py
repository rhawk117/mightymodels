"""The task rows with their attempts, failed fixes and status transitions."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Command, Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class TaskStatus(StrEnum):
    PENDING = 'pending'
    IN_PROGRESS = 'in-progress'
    VERIFIED = 'verified'
    FAILED = 'failed'
    BLOCKED = 'blocked'
    SUPERSEDED = 'superseded'


class Worker(StrEnum):
    ENGINEER = 'engineer'
    ARCHITECT = 'architect'
    INTERN = 'intern'


class ArchitectMode(StrEnum):
    RECOVERY_IMPLEMENTATION = 'recovery-implementation'
    SYSTEMIC_REFACTOR = 'systemic-refactor'
    DIAGNOSE_REPLAN = 'diagnose-replan'


class TaskKeyParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int
    task_key: str


class TicketTaskCountParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int


class TicketTasksParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int
    limit: int


class StartedByParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int
    worker: Worker
    limit: int


class UpsertTaskParams(Struct, frozen=True, kw_only=True):
    ticket_id: int
    task_key: str
    status: TaskStatus
    owned: list[str]
    base: str | None
    commit: str | None
    reasons: list[str]
    updated_at: datetime


class RecordTaskVerificationParams(Struct, frozen=True, kw_only=True):
    ticket_id: int
    task_key: str
    status: TaskStatus
    commit: str
    reasons: list[str]
    updated_at: datetime


class AddTaskAttemptParams(Struct, frozen=True, kw_only=True, gc=False):
    task_id: int
    worker: Worker
    mode: ArchitectMode | None
    at: datetime


class AttemptsInModesParams(Struct, frozen=True, kw_only=True):
    task_id: int
    modes: list[ArchitectMode]


class AddTaskFailedFixParams(Struct, frozen=True, kw_only=True, gc=False):
    task_id: int
    hypothesis: str
    at: datetime


class TaskFailedFixesParams(Struct, frozen=True, kw_only=True, gc=False):
    task_id: int
    limit: int


class AddTaskTransitionParams(Struct, frozen=True, kw_only=True):
    task_id: int
    before: TaskStatus
    after: TaskStatus
    reasons: list[str]
    head: str | None
    at: datetime


class TransitionsIntoParams(Struct, frozen=True, kw_only=True):
    ticket_id: int
    statuses: list[TaskStatus]
    limit: int


class TaskIdRow(Struct, frozen=True, kw_only=True, gc=False):
    id: int


class TaskRow(Struct, frozen=True, kw_only=True):
    id: int
    task_key: str
    status: TaskStatus
    owned: list[str]
    base: str | None
    commit: str | None
    reasons: list[str]
    updated_at: datetime


class TaskCountRow(Struct, frozen=True, kw_only=True, gc=False):
    count: int


class TaskKeyRow(Struct, frozen=True, kw_only=True, gc=False):
    task_key: str


class AttemptCountRow(Struct, frozen=True, kw_only=True, gc=False):
    task_key: str
    worker: Worker
    attempts: int


class FailedFixRow(Struct, frozen=True, kw_only=True, gc=False):
    hypothesis: str


class TransitionRow(Struct, frozen=True, kw_only=True):
    task_key: str
    before: TaskStatus
    after: TaskStatus
    reasons: list[str]
    head: str | None
    at: datetime


TASK_BY_KEY = Query(name='task_by_key', params=TaskKeyParams, row=TaskRow)
TASKS_OF_TICKET = Query(name='tasks_of_ticket', params=TicketTasksParams, row=TaskRow)
TASK_COUNT = Query(name='task_count', params=TicketTaskCountParams, row=TaskCountRow)
IN_PROGRESS_TASKS_STARTED_BY = Query(
    name='in_progress_tasks_started_by', params=StartedByParams, row=TaskKeyRow
)
UPSERT_TASK = Query(name='upsert_task', params=UpsertTaskParams, row=TaskIdRow)
RECORD_TASK_VERIFICATION = Query(
    name='record_task_verification', params=RecordTaskVerificationParams, row=TaskIdRow
)
ADD_TASK_ATTEMPT = Command(name='add_task_attempt', params=AddTaskAttemptParams)
ATTEMPTS_BY_WORKER = Query(name='attempts_by_worker', params=TicketTasksParams, row=AttemptCountRow)
ATTEMPTS_IN_MODES = Query(name='attempts_in_modes', params=AttemptsInModesParams, row=TaskCountRow)
ADD_TASK_FAILED_FIX = Command(name='add_task_failed_fix', params=AddTaskFailedFixParams)
TASK_FAILED_FIXES = Query(name='task_failed_fixes', params=TaskFailedFixesParams, row=FailedFixRow)
ADD_TASK_TRANSITION = Command(name='add_task_transition', params=AddTaskTransitionParams)
LATEST_TRANSITIONS_INTO = Query(
    name='latest_transitions_into', params=TransitionsIntoParams, row=TransitionRow
)
LATEST_TRANSITION_OF_EACH_TASK_INTO = Query(
    name='latest_transition_of_each_task_into', params=TransitionsIntoParams, row=TransitionRow
)

DECLARATIONS: tuple[Declaration, ...] = (
    TASK_BY_KEY,
    TASKS_OF_TICKET,
    TASK_COUNT,
    IN_PROGRESS_TASKS_STARTED_BY,
    UPSERT_TASK,
    RECORD_TASK_VERIFICATION,
    ADD_TASK_ATTEMPT,
    ATTEMPTS_BY_WORKER,
    ATTEMPTS_IN_MODES,
    ADD_TASK_FAILED_FIX,
    TASK_FAILED_FIXES,
    ADD_TASK_TRANSITION,
    LATEST_TRANSITIONS_INTO,
    LATEST_TRANSITION_OF_EACH_TASK_INTO,
)
