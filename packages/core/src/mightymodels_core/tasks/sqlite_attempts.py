"""The attempt repository over a core unit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import TaskId, redact
from mightymodels_core.schemas.tasks import (
    ADD_TASK_FAILED_FIX,
    ATTEMPTS_BY_WORKER,
    ATTEMPTS_IN_MODES,
    LATEST_TRANSITION_OF_EACH_TASK_INTO,
    LATEST_TRANSITIONS_INTO,
    TASK_BY_KEY,
    TASK_FAILED_FIXES,
    AddTaskFailedFixParams,
    AttemptsInModesParams,
    TaskFailedFixesParams,
    TaskKeyParams,
    TicketTasksParams,
    TransitionsIntoParams,
)
from mightymodels_core.tasks.errors import UnknownTaskError
from mightymodels_core.tasks.records import (
    ATTEMPT_COUNTS,
    FAILED_FIXES,
    TASKS,
    Transition,
)

if TYPE_CHECKING:
    from collections.abc import Collection

    from mightymodels_core.database import Unit
    from mightymodels_core.primitives import RedactedText
    from mightymodels_core.schemas.tasks import ArchitectMode, TaskStatus, TransitionRow
    from mightymodels_core.tasks.records import AttemptCounts, FailedFix


def transition_of(row: TransitionRow) -> Transition:
    return Transition(
        task_key=TaskId(row.task_key),
        before=row.before,
        after=row.after,
        reasons=tuple(redact(reason) for reason in row.reasons),
        head=row.head,
        at=row.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteAttemptRepository:
    unit: Unit

    def attempts_by_worker(self, ticket_id: int) -> AttemptCounts:
        params = TicketTasksParams(ticket_id=ticket_id, limit=ATTEMPT_COUNTS.fetched)
        rows = self.unit.all(ATTEMPTS_BY_WORKER, params)
        if (error := ATTEMPT_COUNTS.error(rows, owner=f'ticket {ticket_id}')) is not None:
            raise error

        counts: AttemptCounts = {}
        for row in rows:
            counts.setdefault(TaskId(row.task_key), {})[row.worker] = row.attempts
        return counts

    def attempts_in_modes(
        self, ticket_id: int, task_key: TaskId, modes: Collection[ArchitectMode]
    ) -> int:
        task_id = self.task_id_of(ticket_id, task_key)
        if task_id is None:
            return 0

        params = AttemptsInModesParams(task_id=task_id, modes=sorted(modes))
        (row,) = self.unit.all(ATTEMPTS_IN_MODES, params)
        return row.count

    def failed_fixes(self, ticket_id: int, task_key: TaskId) -> list[RedactedText]:
        task_id = self.task_id_of(ticket_id, task_key)
        if task_id is None:
            return []

        params = TaskFailedFixesParams(task_id=task_id, limit=FAILED_FIXES.fetched)
        rows = self.unit.all(TASK_FAILED_FIXES, params)
        owner = f'task {task_key} of ticket {ticket_id}'
        if (error := FAILED_FIXES.error(rows, owner=owner)) is not None:
            raise error
        return [redact(row.hypothesis) for row in rows]

    def record_failed_fix(self, ticket_id: int, fix: FailedFix) -> None:
        task_id = self.task_id_of(ticket_id, fix.task_key)
        if task_id is None:
            raise UnknownTaskError(ticket_id=ticket_id, task_key=fix.task_key)

        self.unit.run(
            ADD_TASK_FAILED_FIX,
            AddTaskFailedFixParams(task_id=task_id, hypothesis=fix.hypothesis, at=fix.at),
        )

    def latest_transitions_into(
        self, ticket_id: int, statuses: Collection[TaskStatus], limit: int
    ) -> list[Transition]:
        params = TransitionsIntoParams(ticket_id=ticket_id, statuses=sorted(statuses), limit=limit)
        rows = self.unit.all(LATEST_TRANSITIONS_INTO, params)
        return [transition_of(row) for row in reversed(rows)]

    def latest_transition_of_each_task_into(
        self, ticket_id: int, statuses: Collection[TaskStatus]
    ) -> dict[TaskId, Transition]:
        params = TransitionsIntoParams(
            ticket_id=ticket_id, statuses=sorted(statuses), limit=TASKS.fetched
        )
        rows = self.unit.all(LATEST_TRANSITION_OF_EACH_TASK_INTO, params)
        if (error := TASKS.error(rows, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return {TaskId(row.task_key): transition_of(row) for row in rows}

    def task_id_of(self, ticket_id: int, task_key: TaskId) -> int | None:
        row = self.unit.one(TASK_BY_KEY, TaskKeyParams(ticket_id=ticket_id, task_key=task_key))
        return None if row is None else row.id
