"""The ticket decision repository over a real sqlite unit, with a clock the test sets."""

from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS

from tests.core.ticket_decisions.ticket_decisions_builders import DATABASE_FILE, stage_decisions

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database, Unit

    from tests.core.ticket_decisions.ticket_decisions_builders import DecisionsFor, StagedDecisions


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


@pytest.fixture
def decisions_for(unit: Unit) -> DecisionsFor:
    def build(slug: str) -> StagedDecisions:
        return stage_decisions(unit, slug)

    return build
