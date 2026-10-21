"""The seams under the task services: the tasks of one ticket and their attempts, by ticket id.

`TaskRepository` reads and writes the task rows. `record_start` upserts the task as in progress,
keeps the base it first had, and writes the attempt and the transition with it.
`record_verification` sets the verified commit and refuses a task that was never started.
`record_mark` moves a task that may never have started, keeping what it held. A write that leaves
the ticket with more tasks than one read returns is refused.

`AttemptRepository` reads the attempts, failed fixes and transitions the starts and marks wrote.
`failed_fixes` and `latest_transition_of_each_task_into` refuse to answer from part of the rows.
`latest_transitions_into` returns the newest `limit` moves into the statuses, oldest first.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Collection

    from mightymodels_core.primitives import RedactedText, TaskId
    from mightymodels_core.tasks.records import (
        Attempt,
        AttemptCounts,
        FailedFix,
        TaskRecord,
        Transition,
    )
    from mightymodels_core.vocabulary.tasks import ArchitectMode, TaskStatus, Worker


@runtime_checkable
class TaskRepository(Protocol):
    def task(self, ticket_id: int, task_key: TaskId) -> TaskRecord | None: ...

    def tasks(self, ticket_id: int) -> list[TaskRecord]: ...

    def in_progress_started_by(self, ticket_id: int, worker: Worker) -> list[TaskId]: ...

    def record_start(self, ticket_id: int, transition: Transition, attempt: Attempt) -> None: ...

    def record_verification(self, ticket_id: int, transition: Transition, commit: str) -> None: ...

    def record_mark(self, ticket_id: int, transition: Transition) -> None: ...


@runtime_checkable
class AttemptRepository(Protocol):
    def attempts_by_worker(self, ticket_id: int) -> AttemptCounts: ...

    def attempts_in_modes(
        self, ticket_id: int, task_key: TaskId, modes: Collection[ArchitectMode]
    ) -> int: ...

    def failed_fixes(self, ticket_id: int, task_key: TaskId) -> list[RedactedText]: ...

    def record_failed_fix(self, ticket_id: int, fix: FailedFix) -> None: ...

    def latest_transitions_into(
        self, ticket_id: int, statuses: Collection[TaskStatus], limit: int
    ) -> list[Transition]: ...

    def latest_transition_of_each_task_into(
        self, ticket_id: int, statuses: Collection[TaskStatus]
    ) -> dict[TaskId, Transition]: ...
