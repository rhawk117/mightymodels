from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, open_database
from mightymodels_core.edge import create_database_spec
from mightymodels_core.primitives import RepositoryKey, Slug
from mightymodels_core.primitives.tests.clock import create_fake_clock
from mightymodels_core.tickets import TicketAnswers
from mightymodels_core.units_of_work import TicketWork
from mightymodels_core.workspace import workspace_at

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database
    from mightymodels_core.workspace import Workspace


@pytest.fixture
def repository_key() -> RepositoryKey:
    return RepositoryKey('owner/repo')


@pytest.fixture
def database(tmp_path: Path) -> Generator[Database]:
    opened = open_database(
        tmp_path.joinpath('mightymodels.db'), create_database_spec(), ConnectionOptions()
    )
    yield opened
    opened.close()


@pytest.fixture
def slug() -> Slug:
    return Slug('add-widget')


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return workspace_at(tmp_path.joinpath('project'))


@pytest.fixture
def ticket_work(
    database: Database, repository_key: RepositoryKey, workspace: Workspace
) -> TicketWork:
    return TicketWork(
        database=database,
        repository_key=repository_key,
        workspace=workspace,
        clock=create_fake_clock(datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)),
    )


@pytest.fixture
def answers() -> TicketAnswers:
    return TicketAnswers(
        summary='add the widget',
        context=('one line', 'two lines'),
        scope='large',
        plan_first=True,
        branch='feat/widget',
    )


@pytest.fixture
def written_text(ticket_work: TicketWork, slug: Slug, answers: TicketAnswers) -> str:
    with ticket_work.write() as unit:
        text = unit.tickets.write(slug, answers, unit.files.slot(slug))
        unit.store(slug, text)
    return text
