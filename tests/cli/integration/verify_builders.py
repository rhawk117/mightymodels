"""A real repository and state database for `verify run`: seeded and read back through core."""

import asyncio
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.contract import ApprovedCommand
from mightymodels_core.edge import create_clock, open_state
from mightymodels_core.primitives import Slug
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import TaskWork, write_entry

from tests.core.tasks.repository_builders import create_ticket_section

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

SLUG = Slug('port-cli')
COMMAND_KEY = 'I1'
PASSED = 0
REFUSED = 2
VERIFY_RUN = ['verify', 'run', '--slug', str(SLUG), '--all']
SQLITE_HEADER = b'SQLite format 3\x00'
PASSING_ARGV = (sys.executable, '-c', 'pass')
OLD_TABLES = (
    'CREATE TABLE tickets (slug VARCHAR NOT NULL, status VARCHAR NOT NULL, PRIMARY KEY (slug))',
    "INSERT INTO tickets VALUES ('retry-queue', 'staged')",
    'CREATE TABLE contract_commands (slug VARCHAR NOT NULL, command_id VARCHAR NOT NULL)',
    "INSERT INTO contract_commands VALUES ('retry-queue', 'I1')",
)


def tree(top: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(top)): path.read_bytes()
        for path in sorted(top.rglob('*'))
        if path.is_file()
    }


def sqlite_files_below(top: Path) -> list[str]:
    return [name for name, content in tree(top).items() if content.startswith(SQLITE_HEADER)]


def sqlite_file(file: Path, statements: Sequence[str]) -> Path:
    file.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(file)) as connection:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    return file


@dataclass(slots=True, kw_only=True, frozen=True)
class KeptFile:
    file: Path
    content: bytes

    def is_as_it_was(self) -> bool:
        return self.file.read_bytes() == self.content

    def has_nothing_beside_it(self) -> bool:
        return sorted(path.name for path in self.file.parent.iterdir()) == [self.file.name]


def kept(file: Path) -> KeptFile:
    return KeptFile(file=file, content=file.read_bytes())


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedStart:
    top: Path
    files_before: dict[str, bytes]

    def created_nothing(self) -> bool:
        return tree(self.top) == self.files_before


def refused_start(top: Path) -> RefusedStart:
    return RefusedStart(top=top, files_before=tree(top))


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovedContract:
    repository: Path
    data_directory: Path

    def approve(self, argv: Sequence[str] = PASSING_ARGV, key: str = COMMAND_KEY) -> None:
        asyncio.run(self.approve_in_state(argv, key))

    def stage(self) -> None:
        asyncio.run(self.stage_in_state())

    def receipts(self) -> list[str]:
        return asyncio.run(self.receipts_in_state())

    async def stage_in_state(self) -> None:
        async with open_state(self.data_directory, self.repository) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
                tickets.stage(SLUG, create_ticket_section(SLUG), ())

    async def approve_in_state(self, argv: Sequence[str], key: str) -> None:
        command = ApprovedCommand(
            key=key, argv=tuple(argv), expect_exit=0, timeout=60, approved_by='user'
        )
        await self.stage_in_state()
        async with open_state(self.data_directory, self.repository) as state:
            repository_key = state.checkout.repository_key()
            work = TaskWork(
                database=state.database, repository_key=repository_key, clock=create_clock()
            )
            with work.write() as unit:
                unit.contracts.approve(SLUG, [command], await state.git.resolve_head())

    async def receipts_in_state(self) -> list[str]:
        async with open_state(self.data_directory, self.repository) as state:
            work = TaskWork(
                database=state.database,
                repository_key=state.checkout.repository_key(),
                clock=create_clock(),
            )
            with work.read() as unit:
                status = unit.contracts.status(SLUG, await state.git.resolve_head())
        return [
            f'{held.command.key} {held.assessment.state} {held.assessment.outcome_at_head}'
            for held in status.commands
        ]
