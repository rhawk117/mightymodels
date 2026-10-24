"""The ticket repository over a real sqlite unit and over the fake, one fixture for both."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.investigations import ADD_INVESTIGATION, AddInvestigationParams
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.tickets import (
    SqliteTicketRepository,
    TicketService,
    TicketSlot,
)

from tests.core.primitives.clock import create_fake_clock
from tests.core.tickets.fakes import FakeTicketRepository
from tests.core.tickets.ticket_builders import (
    RECORDED_INVESTIGATIONS,
    SERVICE_MOMENT,
    SQL,
    create_answers,
    create_fake_investigations,
    create_free_slot,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.tickets import TicketAnswers, TicketRepository

    from tests.core.investigations.fakes import FakeInvestigationRepository
    from tests.core.primitives.clock import FakeClock


def repository_implementation_params() -> list[ParameterSet]:
    return [
        pytest.param('sqlite_repository', id='sqlite', marks=pytest.mark.integration),
        pytest.param('fake_repository', id='fake'),
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
def repository_id(database: Database) -> int:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        for key in RECORDED_INVESTIGATIONS:
            params = AddInvestigationParams(
                repository_id=repository.id, investigation_key=key, target='target', kind='code'
            )
            unit.one(ADD_INVESTIGATION, params)
    return repository.id


@pytest.fixture
def sqlite_repository(database: Database, repository_id: int) -> Generator[TicketRepository]:
    with database.write() as unit:
        yield SqliteTicketRepository(unit=unit, repository_id=repository_id)


@pytest.fixture
def fake_repository() -> TicketRepository:
    return FakeTicketRepository(recorded_investigations=RECORDED_INVESTIGATIONS)


@pytest.fixture(params=repository_implementation_params())
def repository(request: SubRequest) -> TicketRepository:
    return request.getfixturevalue(request.param)


@pytest.fixture
def fake_investigations() -> FakeInvestigationRepository:
    return create_fake_investigations()


@pytest.fixture
def clock() -> FakeClock:
    return create_fake_clock(SERVICE_MOMENT)


@pytest.fixture
def service(
    fake_repository: TicketRepository,
    fake_investigations: FakeInvestigationRepository,
    clock: FakeClock,
) -> TicketService:
    return TicketService(tickets=fake_repository, investigations=fake_investigations, clock=clock)


@pytest.fixture
def answers() -> TicketAnswers:
    return create_answers()


@pytest.fixture
def surrogate_answers() -> TicketAnswers:
    return create_answers(summary='broken \ud800 text')


@pytest.fixture
def unrecorded_answers() -> TicketAnswers:
    return create_answers(investigations=('never-added',))


@pytest.fixture
def free_slot() -> TicketSlot:
    return create_free_slot()


@pytest.fixture
def taken_slot() -> TicketSlot:
    return TicketSlot(path='.mightymodels/add-widget/ticket.yml', exists=True)
