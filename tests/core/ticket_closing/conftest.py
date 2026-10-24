"""The closing repository over a real sqlite unit and over the fake, one fixture for both."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import TICKET_BY_SLUG, TicketSlugParams
from mightymodels_core.ticket_closing import SqliteClosingRepository
from mightymodels_core.tickets import SqliteTicketRepository

from tests.core.ticket_closing.closing_builders import (
    FAKE_TICKET_ID,
    SQL,
    TICKET_SLUG,
    ClosingHarness,
    create_ticket_section,
)
from tests.core.ticket_closing.fakes import FakeClosingRepository

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database


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
