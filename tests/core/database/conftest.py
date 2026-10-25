"""A tiny fixture database for the database adapter tests."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import (
    Command,
    ConnectionOptions,
    DatabaseSpec,
    Query,
    open_database,
)

from tests.core.database.database_builders import (
    FIXTURE_SCHEMA,
    FIXTURE_STATEMENTS,
    NamePart,
    NameRow,
    create_statements,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database

    from tests.core.database.database_builders import Statements


@pytest.fixture
def find_name() -> Query[NamePart, NameRow]:
    return Query(name='find_name', params=NamePart, row=NameRow)


@pytest.fixture
def rename() -> Command[NamePart]:
    return Command(name='rename', params=NamePart)


@pytest.fixture
def statements() -> Statements:
    return create_statements()


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path.joinpath('fixture.db')


@pytest.fixture
def database_spec(tmp_path: Path, statements: Statements) -> DatabaseSpec:
    schema = tmp_path.joinpath('schema.sql')
    schema.write_text(FIXTURE_SCHEMA, encoding='utf-8')
    statement_file = tmp_path.joinpath('statements.sql')
    statement_file.write_text(FIXTURE_STATEMENTS, encoding='utf-8')
    return DatabaseSpec(
        schema=schema,
        statements=statement_file,
        declarations=statements.declarations,
    )


@pytest.fixture
def database(database_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(database_path, database_spec, ConnectionOptions())
    yield opened
    opened.close()
