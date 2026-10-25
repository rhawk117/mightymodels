"""Builders and the harness for the task and attempt repository tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

from mightymodels_core.primitives import Slug, TaskId, redact
from mightymodels_core.tasks import Attempt, Transition
from mightymodels_core.tickets import TicketSection, Tracker

if TYPE_CHECKING:
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks import AttemptRepository, TaskRepository

SQL = files('mightymodels_core.sql')
SECOND_TASK = TaskId('T2')
TICKET_SLUGS = (Slug('tasks-subject'), Slug('other-subject'))
FAKE_TICKET_IDS = (1, 2)


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


def create_ticket_section(slug: Slug) -> TicketSection:
    return TicketSection(
        ticket=f'.mightymodels/{slug}/ticket.yml',
        summary=redact('a summary'),
        branch='main',
        scope='med',
        plan_first=False,
        auto_escalate=False,
        models={'engineer': 'sonnet'},
        tracker=Tracker(issue=None, jira=None),
        context=(),
        validated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
