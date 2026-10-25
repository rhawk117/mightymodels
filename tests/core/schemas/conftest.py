"""The real schema, statement catalogue and declarations opened through the adapter."""

from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database, parse_blocks
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import (
    ENSURE_REPOSITORY,
    RepositoryKeyParams,
)
from mightymodels_core.schemas.tickets import STAGE_TICKET, StageTicketParams

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path.joinpath('mightymodels.db')


@pytest.fixture(scope='session')
def database_spec() -> DatabaseSpec:
    sql = files('mightymodels_core.sql')
    return DatabaseSpec(
        schema=sql.joinpath('schema.sql'),
        statements=sql.joinpath('statements.sql'),
        declarations=DECLARATIONS,
    )


@pytest.fixture
def database(database_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(database_path, database_spec, ConnectionOptions())
    yield opened
    opened.close()


@pytest.fixture(scope='module')
def blocks() -> dict[str, str]:
    return parse_blocks(
        files('mightymodels_core.sql').joinpath('statements.sql').read_text(encoding='utf-8')
    )


@pytest.fixture
def repository_id(database: Database) -> int:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
    assert repository is not None
    return repository.id


@pytest.fixture
def ticket_id(database: Database, repository_id: int) -> int:
    params = StageTicketParams(
        repository_id=repository_id,
        slug='staged',
        ticket='a staged ticket',
        summary='summary',
        branch='main',
        scope='med',
        plan_first=False,
        auto_escalate=False,
        issue=None,
        jira=None,
        models={},
        context=[],
        validated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    with database.write() as unit:
        staged = unit.one(STAGE_TICKET, params)
    assert staged is not None
    return staged.id
