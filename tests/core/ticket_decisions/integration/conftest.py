"""The ticket decision repository over a real sqlite unit, with a clock the test sets."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import STAGE_TICKET, StageTicketParams
from mightymodels_core.ticket_decisions import SqliteTicketDecisionRepository

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from mightymodels_core.database import Database, Unit

DATABASE_FILE = 'mightymodels.db'
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@dataclass(slots=True, kw_only=True, frozen=True)
class FixedClock:
    moment: datetime

    def now(self) -> datetime:
        return self.moment


type DecisionsFor = Callable[[str], SqliteTicketDecisionRepository]


@pytest.fixture
def database_spec() -> DatabaseSpec:
    sql = files('mightymodels_core.sql')
    return DatabaseSpec(
        schema=sql.joinpath('schema.sql'),
        statements=sql.joinpath('statements.sql'),
        declarations=DECLARATIONS,
    )


@pytest.fixture
def database(tmp_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(tmp_path.joinpath(DATABASE_FILE), database_spec, ConnectionOptions())
    yield opened
    opened.close()


@pytest.fixture
def unit(database: Database) -> Generator[Unit]:
    with database.write() as opened:
        yield opened


def stage_decisions(unit: Unit, slug: str) -> SqliteTicketDecisionRepository:
    repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
    assert repository is not None
    params = StageTicketParams(
        repository_id=repository.id,
        slug=slug,
        ticket=f'ticket {slug}',
        summary='summary',
        branch='main',
        scope='med',
        plan_first=False,
        auto_escalate=False,
        issue=None,
        jira=None,
        models={},
        context=[],
        validated_at=NOW,
    )
    staged = unit.one(STAGE_TICKET, params)
    assert staged is not None
    return SqliteTicketDecisionRepository(
        unit=unit, ticket_id=staged.id, clock=FixedClock(moment=NOW)
    )


@pytest.fixture
def decisions_for(unit: Unit) -> DecisionsFor:
    def build(slug: str) -> SqliteTicketDecisionRepository:
        return stage_decisions(unit, slug)

    return build
