"""The connection manager: one SQLite file, its schema applied and its statements bound.

The connection runs in autocommit mode for life and is shared behind an instance-owned lock.
`read()` and `write()` are the only way to run a declared statement.
"""

import re
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .catalogue import bind_catalogue
from .errors import (
    DatabaseInUseError,
    SchemaVersionError,
    UnversionedSchemaError,
    translate_errors,
)
from .units import READ_UNIT, WRITE_UNIT, Channel, UnitScope

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable
    from pathlib import Path

    from .statements import Declaration

SCRIPT_VERSION = re.compile(
    r'^[ \t]*PRAGMA[ \t]+user_version[ \t]*=[ \t]*(?P<version>\d+)[ \t]*;?[ \t]*$',
    re.IGNORECASE | re.MULTILINE,
)


class JournalMode(StrEnum):
    DELETE = 'DELETE'
    TRUNCATE = 'TRUNCATE'
    PERSIST = 'PERSIST'
    MEMORY = 'MEMORY'
    WAL = 'WAL'
    OFF = 'OFF'


class Synchronous(StrEnum):
    OFF = 'OFF'
    NORMAL = 'NORMAL'
    FULL = 'FULL'
    EXTRA = 'EXTRA'


@dataclass(slots=True, kw_only=True, frozen=True)
class ConnectionOptions:
    foreign_keys: bool = True
    journal_mode: JournalMode = JournalMode.WAL
    synchronous: Synchronous = Synchronous.NORMAL
    busy_timeout_seconds: float = 10.0

    @property
    def foreign_keys_pragma(self) -> str:
        return 'ON' if self.foreign_keys else 'OFF'


DEFAULT_OPTIONS = ConnectionOptions()


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseSpec:
    schema: Traversable
    statements: Traversable
    declarations: tuple[Declaration, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class Schema:
    script: str
    version: int


def parse_schema(script: str) -> Schema:
    versions = SCRIPT_VERSION.findall(script)
    if not versions:
        raise UnversionedSchemaError

    return Schema(script=script, version=int(versions[-1]))


def read_user_version(connection: sqlite3.Connection) -> int:
    with translate_errors('PRAGMA user_version'):
        return int(connection.execute('PRAGMA user_version').fetchone()[0])


def configure(connection: sqlite3.Connection, options: ConnectionOptions) -> None:
    pragmas = (
        f'PRAGMA foreign_keys = {options.foreign_keys_pragma}',
        f'PRAGMA journal_mode = {options.journal_mode}',
        f'PRAGMA synchronous = {options.synchronous}',
    )
    with translate_errors('PRAGMA'):
        for pragma in pragmas:
            connection.execute(pragma)


def run_install(connection: sqlite3.Connection, script: str) -> None:
    if read_user_version(connection) == 0:
        with translate_errors('schema'):
            connection.executescript(script)

    with translate_errors('COMMIT'):
        connection.execute('COMMIT')


def install_schema(connection: sqlite3.Connection, script: str) -> None:
    with translate_errors('BEGIN IMMEDIATE'):
        connection.execute('BEGIN IMMEDIATE')

    try:
        run_install(connection, script)
    except BaseException:
        if connection.in_transaction:
            with translate_errors('ROLLBACK'):
                connection.execute('ROLLBACK')
        raise


def apply_schema(connection: sqlite3.Connection, schema: Schema) -> None:
    if read_user_version(connection) == 0:
        install_schema(connection, schema.script)

    found = read_user_version(connection)
    if found != schema.version:
        raise SchemaVersionError(found=found, expected=schema.version)


def prepare(connection: sqlite3.Connection, schema: Schema, options: ConnectionOptions) -> None:
    configure(connection, options)
    apply_schema(connection, schema)


def prepare_or_close(
    connection: sqlite3.Connection, schema: Schema, options: ConnectionOptions
) -> None:
    try:
        prepare(connection, schema, options)
    except BaseException:
        with translate_errors('close'):
            connection.close()
        raise


@dataclass(slots=True, kw_only=True)
class Database:
    channel: Channel

    def read(self) -> UnitScope:
        return UnitScope(channel=self.channel, kind=READ_UNIT)

    def write(self) -> UnitScope:
        return UnitScope(channel=self.channel, kind=WRITE_UNIT)

    def close(self) -> None:
        if not self.channel.lock.acquire(blocking=False):
            raise DatabaseInUseError

        try:
            self.channel.is_closed = True
            with translate_errors('close'):
                self.channel.connection.close()
        finally:
            self.channel.lock.release()


def open_database(
    path: Path,
    spec: DatabaseSpec,
    options: ConnectionOptions = DEFAULT_OPTIONS,
) -> Database:
    catalogue = bind_catalogue(spec.statements.read_text(encoding='utf-8'), spec.declarations)
    schema = parse_schema(spec.schema.read_text(encoding='utf-8'))
    with translate_errors('open'):
        connection = sqlite3.connect(
            path,
            timeout=options.busy_timeout_seconds,
            autocommit=True,
            check_same_thread=False,
        )

    prepare_or_close(connection, schema, options)
    return Database(channel=Channel(connection=connection, catalogue=catalogue))
