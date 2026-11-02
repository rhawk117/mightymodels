import os
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mightymodels_core.database.connection import parse_schema
from mightymodels_core.edge import DATABASE_NAME, create_database_spec

from tests.mcp.journal.journal_harness import FIRST_ENTRY

if TYPE_CHECKING:
    from mcp.types import CallToolResult

    from tests.mcp.server.server_harness import ServerHarness

CONSOLE_SCRIPT = Path(sys.executable).with_name('mightymodels-mcp')
SLUG = 'upgrade-probe'


def create_database(path: Path, version: int) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('PRAGMA journal_mode = WAL')
        connection.execute(f'PRAGMA user_version = {version}')
        connection.execute('CREATE TABLE legacy (id INTEGER PRIMARY KEY)')
        connection.commit()


def result_text(result: CallToolResult) -> str:
    return '\n'.join(str(block) for block in result.content)


@dataclass(slots=True, kw_only=True, frozen=True)
class StoredDatabase:
    path: Path


def expected_schema_version() -> int:
    return parse_schema(create_database_spec().schema.read_text(encoding='utf-8')).version


class TestUpgrade:
    @pytest.fixture
    def parameters(self, server_harness: ServerHarness) -> StdioServerParameters:
        inherited = {name: os.environ[name] for name in ('PATH', 'HOME') if name in os.environ}
        return StdioServerParameters(
            command=str(CONSOLE_SCRIPT),
            env={**inherited, **server_harness.environ},
            cwd=server_harness.repository,
        )

    @pytest.fixture
    def stored(self, server_harness: ServerHarness) -> StoredDatabase:
        server_harness.data_directory.mkdir(parents=True)
        return StoredDatabase(path=server_harness.data_directory.joinpath(DATABASE_NAME))

    @pytest.fixture
    def old_plugin(self, stored: StoredDatabase) -> StoredDatabase:
        return StoredDatabase(path=stored.path.with_name('mightymodels.db'))

    async def show_ticket(self, parameters: StdioServerParameters) -> CallToolResult:
        async with Client(parameters) as client:
            return await client.call_tool('ticket_show', {'slug': SLUG})

    async def add_crashout(self, parameters: StdioServerParameters) -> CallToolResult:
        async with Client(parameters) as client:
            return await client.call_tool('crashout_add', dict(FIRST_ENTRY))

    async def test_old_plugin_database_is_left_untouched_and_state_database_starts_fresh(
        self, parameters: StdioServerParameters, stored: StoredDatabase, old_plugin: StoredDatabase
    ) -> None:
        create_database(old_plugin.path, 1)
        before = old_plugin.path.read_bytes()

        result = await self.add_crashout(parameters)

        assert not result.is_error
        assert 'schema version' not in result_text(result)
        assert old_plugin.path.read_bytes() == before
        with closing(sqlite3.connect(stored.path)) as connection:
            assert connection.execute('PRAGMA user_version').fetchone()[0] == (
                expected_schema_version()
            )

    async def test_newer_database_is_left_untouched(
        self, parameters: StdioServerParameters, stored: StoredDatabase
    ) -> None:
        create_database(stored.path, expected_schema_version() + 1)
        before = stored.path.read_bytes()

        result = await self.show_ticket(parameters)

        assert result.is_error
        assert stored.path.read_bytes() == before
