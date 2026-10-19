"""The ticket repository over a real sqlite unit and over the fake, one fixture for both."""

from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.investigations import InvestigationRecord
from mightymodels_core.investigations.tests.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.primitives.tests.clock import create_fake_clock
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.investigations import ADD_INVESTIGATION, AddInvestigationParams
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.tickets import (
    SqliteTicketRepository,
    TicketAnswers,
    TicketSection,
    TicketService,
    TicketSlot,
    Tracker,
)
from mightymodels_core.tickets.tests.fakes import FakeTicketRepository

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.primitives.tests.clock import FakeClock
    from mightymodels_core.tickets import TicketRepository

SQL = files('mightymodels_core.sql')
RECORDED_INVESTIGATIONS = ('first-look', 'second-look')
SERVICE_MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)


def create_section(slug: Slug, branch: str) -> TicketSection:
    return TicketSection(
        ticket=f'.mightymodels/{slug}/ticket.yml',
        summary=redact(f'summary of {slug}'),
        branch=branch,
        scope='med',
        plan_first=False,
        auto_escalate=False,
        models={'engineer': 'sonnet'},
        tracker=Tracker(issue=None, jira=None),
        context=('one', 'two'),
        validated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


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
    ledger = InvestigationLedger()
    investigations = FakeInvestigationRepository(ledger=ledger)
    for key in RECORDED_INVESTIGATIONS:
        record = InvestigationRecord(key=Slug(key), target=redact(key), kind='behavior')
        investigations.add_investigation(record)
    return investigations


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


def create_answers(
    *,
    summary: str = 'add the widget',
    context: tuple[str, ...] = ('one line', 'two lines'),
    investigations: tuple[str, ...] = ('first-look',),
) -> TicketAnswers:
    return TicketAnswers(
        summary=summary,
        context=context,
        scope='large',
        plan_first=True,
        branch='feat/widget',
        issue=7,
        jira='WID-1',
        reference_urls=('https://example.com/a', 'https://example.com/b'),
        investigations=investigations,
    )


@pytest.fixture
def answers() -> TicketAnswers:
    return create_answers()


@pytest.fixture
def unrecorded_answers() -> TicketAnswers:
    return create_answers(investigations=('never-added',))


@pytest.fixture
def free_slot() -> TicketSlot:
    return TicketSlot(path='.mightymodels/add-widget/ticket.yml', exists=False)


@pytest.fixture
def taken_slot() -> TicketSlot:
    return TicketSlot(path='.mightymodels/add-widget/ticket.yml', exists=True)
