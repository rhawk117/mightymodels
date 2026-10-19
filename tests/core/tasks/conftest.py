"""The task and attempt repositories over a real sqlite unit and over the fakes."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import Slug, TaskId, redact
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import TICKET_BY_SLUG, TicketSlugParams
from mightymodels_core.tasks import (
    Attempt,
    SqliteAttemptRepository,
    SqliteTaskRepository,
    Transition,
)
from mightymodels_core.tasks.tests.fakes import (
    FakeAttemptRepository,
    FakeTaskRepository,
    TaskLedger,
)
from mightymodels_core.tickets import SqliteTicketRepository, TicketSection, Tracker

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks import AttemptRepository, TaskRepository

SQL = files('mightymodels_core.sql')
TICKET_SLUGS = (Slug('tasks-subject'), Slug('other-subject'))
FAKE_TICKET_IDS = (1, 2)
FIRST_TASK = TaskId('T1')
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


def create_ticket_section(slug: Slug) -> TicketSection:
    return TicketSection(
        ticket=redact(f'ticket {slug}'),
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


def task_implementation_cases() -> list[ParameterSet]:
    return [
        pytest.param('sqlite_harness', id='sqlite', marks=pytest.mark.integration),
        pytest.param('fake_harness', id='fake'),
    ]


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path.joinpath('mightymodels.db')


@pytest.fixture
def database_spec() -> DatabaseSpec:
    return DatabaseSpec(
        schema=SQL.joinpath('schema.sql'),
        statements=SQL.joinpath('statements.sql'),
        declarations=DECLARATIONS,
    )


@pytest.fixture
def database(database_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(database_path, database_spec, ConnectionOptions())
    yield opened
    opened.close()


@pytest.fixture
def staged_ticket_ids(database: Database) -> tuple[int, int]:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        tickets = SqliteTicketRepository(unit=unit, repository_id=repository.id)
        ids: list[int] = []
        for slug in TICKET_SLUGS:
            tickets.stage(slug, create_ticket_section(slug), ())
            row = unit.one(TICKET_BY_SLUG, TicketSlugParams(repository_id=repository.id, slug=slug))
            assert row is not None
            ids.append(row.id)
    first, second = ids
    return first, second


@pytest.fixture
def sqlite_harness(
    database: Database, staged_ticket_ids: tuple[int, int]
) -> Generator[TaskHarness]:
    ticket_id, other_ticket_id = staged_ticket_ids
    with database.write() as unit:
        yield TaskHarness(
            tasks=SqliteTaskRepository(unit=unit),
            attempts=SqliteAttemptRepository(unit=unit),
            ticket_id=ticket_id,
            other_ticket_id=other_ticket_id,
        )


@pytest.fixture
def fake_harness() -> TaskHarness:
    ledger = TaskLedger()
    ticket_id, other_ticket_id = FAKE_TICKET_IDS
    return TaskHarness(
        tasks=FakeTaskRepository(ledger=ledger),
        attempts=FakeAttemptRepository(ledger=ledger),
        ticket_id=ticket_id,
        other_ticket_id=other_ticket_id,
    )


@pytest.fixture(params=task_implementation_cases())
def harness(request: SubRequest) -> TaskHarness:
    return request.getfixturevalue(request.param)
