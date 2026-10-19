"""The ticket repository over a real sqlite unit and over the fake, one fixture for both."""

from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import redact
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.investigations import ADD_INVESTIGATION, AddInvestigationParams
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.tickets import SqliteTicketRepository, TicketSection, Tracker
from mightymodels_core.tickets.tests.fakes import FakeTicketRepository

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Slug
    from mightymodels_core.tickets import TicketRepository

SQL = files('mightymodels_core.sql')
RECORDED_INVESTIGATIONS = ('first-look', 'second-look')


def create_section(slug: Slug, branch: str) -> TicketSection:
    return TicketSection(
        ticket=redact(f'ticket {slug}'),
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
