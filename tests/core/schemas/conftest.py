"""The real schema, statement catalogue and declarations opened through the adapter."""

import sqlite3
from contextlib import closing
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import (
    ENSURE_REPOSITORY,
    RepositoryKeyParams,
)

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
