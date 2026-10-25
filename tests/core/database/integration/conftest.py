"""Session-wide database specs for the property tests."""

import pytest
from mightymodels_core.database import DatabaseSpec

from tests.core.database.database_builders import (
    ECHO,
    FIXTURE_SCHEMA,
    FIXTURE_STATEMENTS,
    create_statements,
)

ECHO_STATEMENTS = """
-- name: echo
SELECT json_object(
    'items', json(:items),
    'mapping', json(:mapping),
    'at', strftime('%Y-%m-%dT%H:%M:%SZ', :at, 'unixepoch'),
    'color', :color,
    'flag', :flag
) AS row;
"""


@pytest.fixture(scope='session')
def shared_database_spec(tmp_path_factory: pytest.TempPathFactory) -> DatabaseSpec:
    directory = tmp_path_factory.mktemp('shared-spec')
    schema = directory.joinpath('schema.sql')
    schema.write_text(FIXTURE_SCHEMA, encoding='utf-8')
    statements = directory.joinpath('statements.sql')
    statements.write_text(FIXTURE_STATEMENTS, encoding='utf-8')
    return DatabaseSpec(
        schema=schema, statements=statements, declarations=create_statements().declarations
    )


@pytest.fixture(scope='session')
def echo_spec(tmp_path_factory: pytest.TempPathFactory) -> DatabaseSpec:
    directory = tmp_path_factory.mktemp('echo-spec')
    schema = directory.joinpath('schema.sql')
    schema.write_text('PRAGMA user_version = 1;', encoding='utf-8')
    statements = directory.joinpath('statements.sql')
    statements.write_text(ECHO_STATEMENTS, encoding='utf-8')
    return DatabaseSpec(schema=schema, statements=statements, declarations=(ECHO,))
