"""The real schema, statement catalogue and declarations opened through the adapter."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import (
    ENSURE_REPOSITORY,
    RepositoryKeyParams,
)
from mightymodels_core.schemas.tickets import STAGE_TICKET, StageTicketParams, TicketScope

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database

SQL = files('mightymodels_core.sql')


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
def plan_connection(
    database_path: Path, database_spec: DatabaseSpec
) -> Generator[sqlite3.Connection]:
    open_database(database_path, database_spec, ConnectionOptions()).close()
    with closing(sqlite3.connect(database_path)) as connection:
        yield connection


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
        scope=TicketScope.MED,
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
