"""Builders and the harness for the task and attempt repository tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.primitives import TaskId, redact
from mightymodels_core.tasks import Attempt, Transition

if TYPE_CHECKING:
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks import AttemptRepository, TaskRepository

SECOND_TASK = TaskId('T2')


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskHarness:
    tasks: TaskRepository
    attempts: AttemptRepository
    ticket_id: int
    other_ticket_id: int


def create_transition(
    task_key: TaskId,
    before: TaskStatus,
    after: TaskStatus,
    *,
    day: int = 2,
    head: str | None = 'abc1234',
    reasons: tuple[str, ...] = (),
) -> Transition:
    return Transition(
        task_key=task_key,
        before=before,
        after=after,
        reasons=tuple(redact(reason) for reason in reasons),
        head=head,
        at=datetime(2026, 1, day, 3, 4, 5, tzinfo=UTC),
    )


def create_attempt(*, owned: tuple[str, ...] = ('src/a.py',)) -> Attempt:
    return Attempt(worker='engineer', mode=None, owned=owned)
