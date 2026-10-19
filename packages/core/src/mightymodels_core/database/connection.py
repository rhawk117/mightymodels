"""The connection manager: one SQLite file, its schema applied and its statements bound.

The connection runs in autocommit mode for life and is shared behind an instance-owned lock.
`read()` and `write()` are the only way to run a declared statement.
"""

import re
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from .catalogue import bind_catalogue
from .errors import (
    PragmaNotAppliedError,
    SchemaVersionError,
    UnversionedSchemaError,
    translate_errors,
)
from .units import READ_UNIT, WRITE_UNIT, Channel, UnitScope

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from importlib.resources.abc import Traversable
    from pathlib import Path

    from .statements import Declaration
    from .units import Unit

SCRIPT_VERSION = re.compile(
    r'^[ \t]*PRAGMA[ \t]+user_version[ \t]*=[ \t]*(?P<version>\d+)[ \t]*;?[ \t]*$',
    re.IGNORECASE | re.MULTILINE,
)


type JournalMode = Literal['DELETE', 'TRUNCATE', 'PERSIST', 'MEMORY', 'WAL', 'OFF']
type Synchronous = Literal['OFF', 'NORMAL', 'FULL', 'EXTRA']


@dataclass(slots=True, kw_only=True, frozen=True)
class ConnectionOptions:
    foreign_keys: bool = True
    journal_mode: JournalMode = 'WAL'
    synchronous: Synchronous = 'NORMAL'
    busy_timeout_seconds: float = 10.0
    connection_class: type[sqlite3.Connection] = sqlite3.Connection

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


def rollback_if_open(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        with translate_errors('ROLLBACK'):
            connection.execute('ROLLBACK')


def install_schema(connection: sqlite3.Connection, script: str) -> None:
    with translate_errors('BEGIN IMMEDIATE'):
        connection.execute('BEGIN IMMEDIATE')

    try:
        run_install(connection, script)
    except BaseException:
        rollback_if_open(connection)
        raise


def apply_schema(connection: sqlite3.Connection, schema: Schema) -> None:
    if read_user_version(connection) == 0:
        install_schema(connection, schema.script)

    found = read_user_version(connection)
    if found != schema.version:
        raise SchemaVersionError(found=found, expected=schema.version)


def read_pragma(connection: sqlite3.Connection, pragma: str) -> str:
    with translate_errors(f'PRAGMA {pragma}'):
        return str(connection.execute(f'PRAGMA {pragma}').fetchone()[0]).upper()


def get_pragma_problem(
    connection: sqlite3.Connection, options: ConnectionOptions
) -> PragmaNotAppliedError | None:
    foreign_keys = 'ON' if read_pragma(connection, 'foreign_keys') == '1' else 'OFF'
    if foreign_keys != options.foreign_keys_pragma:
        return PragmaNotAppliedError(
            pragma='foreign_keys', expected=options.foreign_keys_pragma, found=foreign_keys
        )

    journal_mode = read_pragma(connection, 'journal_mode')
    if journal_mode != options.journal_mode:
        return PragmaNotAppliedError(
            pragma='journal_mode', expected=options.journal_mode, found=journal_mode
        )

    return None


def prepare(connection: sqlite3.Connection, schema: Schema, options: ConnectionOptions) -> None:
    configure(connection, options)
    if problem := get_pragma_problem(connection, options):
        raise problem

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


@runtime_checkable
class Database(Protocol):
    def read(self) -> AbstractContextManager[Unit]: ...

    def write(self) -> AbstractContextManager[Unit]: ...

    def close(self) -> None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteDatabase:
    channel: Channel

    def read(self) -> UnitScope:
        return UnitScope(channel=self.channel, kind=READ_UNIT)

    def write(self) -> UnitScope:
        return UnitScope(channel=self.channel, kind=WRITE_UNIT)

    def close(self) -> None:
        self.channel.close()


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
            factory=options.connection_class,
        )

    prepare_or_close(connection, schema, options)
    return SqliteDatabase(channel=Channel(connection=connection, catalogue=catalogue))
