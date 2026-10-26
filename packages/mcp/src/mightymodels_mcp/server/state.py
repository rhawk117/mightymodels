"""The real state opener: core's `open_state` over one data directory and one start directory."""

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.database.connection import parse_schema
from mightymodels_core.edge import DATABASE_NAME, create_database_spec, open_state

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from pathlib import Path

    from mightymodels_core.edge import OpenState

logger = logging.getLogger(__name__)

SIBLING_SUFFIXES = ('', '-wal', '-shm')


@dataclass(slots=True, kw_only=True, frozen=True)
class LocalStateOpener:
    data_directory: Path
    start: Path

    def open(self) -> AbstractAsyncContextManager[OpenState]:
        return open_state(self.data_directory, self.start)


def expected_schema_version() -> int:
    return parse_schema(create_database_spec().schema.read_text(encoding='utf-8')).version


def read_stored_version(database: Path) -> int:
    with closing(sqlite3.connect(database)) as connection:
        return int(connection.execute('PRAGMA user_version').fetchone()[0])


def discard_outdated_database(data_directory: Path) -> tuple[Path, ...]:
    database = data_directory.joinpath(DATABASE_NAME)
    if not database.is_file():
        return ()

    found = read_stored_version(database)
    expected = expected_schema_version()
    if found == 0 or found >= expected:
        return ()

    siblings = tuple(database.with_name(f'{database.name}{suffix}') for suffix in SIBLING_SUFFIXES)
    for sibling in siblings:
        sibling.unlink(missing_ok=True)

    logger.warning(
        'deleted the schema version %d database %s, starting on a fresh version %d store',
        found,
        database,
        expected,
    )
    return siblings
