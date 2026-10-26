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
from mightymodels_core.edge import DATABASE_NAME
from mightymodels_mcp.server.state import expected_schema_version

if TYPE_CHECKING:
    from mcp.types import CallToolResult

    from tests.mcp.server.server_harness import ServerHarness

CONSOLE_SCRIPT = Path(sys.executable).with_name('mightymodels-mcp')
SIBLING_SUFFIXES = ('-wal', '-shm')
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

    @property
    def siblings(self) -> tuple[Path, ...]:
        return tuple(self.path.with_name(f'{self.path.name}{s}') for s in SIBLING_SUFFIXES)


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

    async def show_ticket(self, parameters: StdioServerParameters) -> CallToolResult:
        async with Client(parameters) as client:
            return await client.call_tool('ticket_show', {'slug': SLUG})

    async def test_older_database_is_deleted_and_the_server_starts_fresh(
        self, parameters: StdioServerParameters, stored: StoredDatabase
    ) -> None:
        create_database(stored.path, expected_schema_version() - 1)
        for sibling in stored.siblings:
            sibling.write_bytes(b'stale')

        result = await self.show_ticket(parameters)

        assert 'schema version' not in result_text(result)
        assert not any(sibling.exists() for sibling in stored.siblings)
        with closing(sqlite3.connect(stored.path)) as connection:
            assert connection.execute('PRAGMA user_version').fetchone()[0] == (
                expected_schema_version()
            )
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'legacy'"
            ).fetchall()
        assert tables == []

    async def test_newer_database_is_left_untouched(
        self, parameters: StdioServerParameters, stored: StoredDatabase
    ) -> None:
        create_database(stored.path, expected_schema_version() + 1)
        before = stored.path.read_bytes()

        result = await self.show_ticket(parameters)

        assert result.is_error
        assert stored.path.read_bytes() == before
