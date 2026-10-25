"""The real schema opened through the adapter."""

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database

from tests.core.sql.sql_builders import SCHEMA, STATEMENTS, create_statements

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database

    from tests.core.sql.sql_builders import Statements


@pytest.fixture(scope='session')
def statements() -> Statements:
    return create_statements()


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path.joinpath('mightymodels.db')


@pytest.fixture(scope='session')
def database_spec(tmp_path_factory: pytest.TempPathFactory, statements: Statements) -> DatabaseSpec:
    statement_file = tmp_path_factory.mktemp('statements').joinpath('statements.sql')
    statement_file.write_text(STATEMENTS, encoding='utf-8')
    return DatabaseSpec(
        schema=SCHEMA,
        statements=statement_file,
        declarations=statements.declarations,
    )


@pytest.fixture
def database(database_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(database_path, database_spec, ConnectionOptions())
    yield opened
    opened.close()


@pytest.fixture
def schema_inspection(
    database_path: Path, database_spec: DatabaseSpec
) -> Generator[sqlite3.Connection]:
    open_database(database_path, database_spec, ConnectionOptions()).close()
    with closing(sqlite3.connect(database_path)) as connection:
        yield connection
