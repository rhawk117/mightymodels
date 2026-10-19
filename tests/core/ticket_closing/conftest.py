"""The closing repository over a real sqlite unit and over the fake, one fixture for both."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import TICKET_BY_SLUG, TicketSlugParams
from mightymodels_core.ticket_closing import ClosingRecord, SqliteClosingRepository
from mightymodels_core.ticket_closing.tests.fakes import FakeClosingRepository
from mightymodels_core.tickets import SqliteTicketRepository, TicketSection, Tracker

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.ticket_closing import ClosingRepository

SQL = files('mightymodels_core.sql')
TICKET_SLUG = Slug('closing-subject')
FAKE_TICKET_ID = 1


@dataclass(slots=True, kw_only=True, frozen=True)
class ClosingHarness:
    repository: ClosingRepository
    ticket_id: int


def create_closing(shipped: str, *, closed_day: int = 2) -> ClosingRecord:
    return ClosingRecord(
        closed_at=datetime(2026, 1, closed_day, 3, 4, 5, tzinfo=UTC),
        head='abc1234',
        shipped=redact(shipped),
        pr='https://example.test/pull/7',
        gotchas=(redact('first gotcha'), redact('second gotcha')),
        archive='archive/closing-subject.tar',
    )


def create_ticket_section() -> TicketSection:
    return TicketSection(
        ticket=redact('a ticket'),
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


def closing_implementation_cases() -> list[ParameterSet]:
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
def staged_ticket_id(database: Database) -> int:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        tickets = SqliteTicketRepository(unit=unit, repository_id=repository.id)
        tickets.stage(TICKET_SLUG, create_ticket_section(), ())
        row = unit.one(
            TICKET_BY_SLUG, TicketSlugParams(repository_id=repository.id, slug=TICKET_SLUG)
        )
        assert row is not None
    return row.id


@pytest.fixture
def sqlite_harness(database: Database, staged_ticket_id: int) -> Generator[ClosingHarness]:
    with database.write() as unit:
        yield ClosingHarness(
            repository=SqliteClosingRepository(unit=unit), ticket_id=staged_ticket_id
        )


@pytest.fixture
def fake_harness() -> ClosingHarness:
    return ClosingHarness(repository=FakeClosingRepository(), ticket_id=FAKE_TICKET_ID)


@pytest.fixture(params=closing_implementation_cases())
def harness(request: SubRequest) -> ClosingHarness:
    return request.getfixturevalue(request.param)
