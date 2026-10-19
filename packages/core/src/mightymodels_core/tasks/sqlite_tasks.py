"""The task repository over a core unit."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from mightymodels_core.primitives import TaskId, redact
from mightymodels_core.schemas.tasks import (
    ADD_TASK_ATTEMPT,
    ADD_TASK_TRANSITION,
    IN_PROGRESS_TASKS_STARTED_BY,
    RECORD_TASK_VERIFICATION,
    TASK_BY_KEY,
    TASK_COUNT,
    TASKS_OF_TICKET,
    UPSERT_TASK,
    AddTaskAttemptParams,
    AddTaskTransitionParams,
    RecordTaskVerificationParams,
    StartedByParams,
    TaskKeyParams,
    TicketTaskCountParams,
    TicketTasksParams,
    UpsertTaskParams,
)
from mightymodels_core.tasks.errors import UnknownTaskError
from mightymodels_core.tasks.records import TASKS, TaskRecord

if TYPE_CHECKING:
    from mightymodels_core.database import Unit
    from mightymodels_core.schemas.tasks import TaskRow, Worker
    from mightymodels_core.tasks.records import Attempt, Transition


def record_of(row: TaskRow) -> TaskRecord:
    return TaskRecord(
        key=TaskId(row.task_key),
        status=row.status,
        owned=tuple(row.owned),
        base=row.base,
        commit=row.commit,
        reasons=tuple(redact(reason) for reason in row.reasons),
    )


def transition_params_of(task_id: int, transition: Transition) -> AddTaskTransitionParams:
    return AddTaskTransitionParams(
        task_id=task_id,
        before=transition.before,
        after=transition.after,
        reasons=list(transition.reasons),
        head=transition.head,
        at=transition.at,
    )


def upsert_params_of(ticket_id: int, transition: Transition, held: TaskRecord) -> UpsertTaskParams:
    return UpsertTaskParams(
        ticket_id=ticket_id,
        task_key=transition.task_key,
        status=transition.after,
        owned=list(held.owned),
        base=held.base,
        commit=held.commit,
        reasons=list(held.reasons),
        updated_at=transition.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteTaskRepository:
    unit: Unit

    def task(self, ticket_id: int, task_key: TaskId) -> TaskRecord | None:
        row = self.unit.one(TASK_BY_KEY, TaskKeyParams(ticket_id=ticket_id, task_key=task_key))
        return None if row is None else record_of(row)

    def tasks(self, ticket_id: int) -> list[TaskRecord]:
        params = TicketTasksParams(ticket_id=ticket_id, limit=TASKS.fetched)
        rows = self.unit.all(TASKS_OF_TICKET, params)
        if (error := TASKS.error(rows, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return [record_of(row) for row in rows]

    def in_progress_started_by(self, ticket_id: int, worker: Worker) -> list[TaskId]:
        params = StartedByParams(ticket_id=ticket_id, worker=worker, limit=TASKS.fetched)
        rows = self.unit.all(IN_PROGRESS_TASKS_STARTED_BY, params)
        if (error := TASKS.error(rows, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return [TaskId(row.task_key) for row in rows]

    def record_start(self, ticket_id: int, transition: Transition, attempt: Attempt) -> None:
        started = TaskRecord(
            key=transition.task_key,
            status=transition.after,
            owned=attempt.owned,
            base=transition.head,
        )
        task_id = self.upsert(upsert_params_of(ticket_id, transition, started))
        self.unit.run(
            ADD_TASK_ATTEMPT,
            AddTaskAttemptParams(
                task_id=task_id, worker=attempt.worker, mode=attempt.mode, at=transition.at
            ),
        )
        self.unit.run(ADD_TASK_TRANSITION, transition_params_of(task_id, transition))
        self.refuse_too_many_tasks(ticket_id)

    def record_verification(self, ticket_id: int, transition: Transition, commit: str) -> None:
        params = RecordTaskVerificationParams(
            ticket_id=ticket_id,
            task_key=transition.task_key,
            status=transition.after,
            commit=commit,
            reasons=list(transition.reasons),
            updated_at=transition.at,
        )
        row = self.unit.one(RECORD_TASK_VERIFICATION, params)
        if row is None:
            raise UnknownTaskError(ticket_id=ticket_id, task_key=transition.task_key)
        self.unit.run(ADD_TASK_TRANSITION, transition_params_of(row.id, transition))

    def record_mark(self, ticket_id: int, transition: Transition) -> None:
        never_started = TaskRecord(key=transition.task_key, status=transition.before)
        held = self.task(ticket_id, transition.task_key) or never_started
        held = replace(held, reasons=transition.reasons)
        task_id = self.upsert(upsert_params_of(ticket_id, transition, held))
        self.unit.run(ADD_TASK_TRANSITION, transition_params_of(task_id, transition))
        self.refuse_too_many_tasks(ticket_id)

    def upsert(self, params: UpsertTaskParams) -> int:
        (row,) = self.unit.all(UPSERT_TASK, params)
        return row.id

    def refuse_too_many_tasks(self, ticket_id: int) -> None:
        (count,) = self.unit.all(TASK_COUNT, TicketTaskCountParams(ticket_id=ticket_id))
        if (error := TASKS.write_error(count.count, owner=f'ticket {ticket_id}')) is not None:
            raise error
