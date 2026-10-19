"""Single-use read and write units of work over the one connection a database owns.

A unit holds the database's lock from entry to exit, so units from different threads run one
at a time. COMMIT and ROLLBACK run as SQL because the connection stays in autocommit mode.
"""

from dataclasses import dataclass, field
from threading import Lock, get_ident
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from msgspec import Struct

from .codec import bind_params, decode_row, decode_rows
from .errors import (
    DatabaseClosedError,
    DatabaseError,
    DatabaseInUseError,
    NestedUnitError,
    SqliteErrorTranslator,
    UnitExitedError,
    UnitReusedError,
    translate_errors,
)

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterable
    from types import TracebackType

    from .catalogue import Catalogue
    from .statements import Command, Declaration, Query


@dataclass(slots=True, kw_only=True)
class Channel:
    connection: sqlite3.Connection
    catalogue: Catalogue
    lock: Lock = field(default_factory=Lock)
    holder: int | None = None
    is_closed: bool = False

    def claim(self) -> None:
        if self.holder == get_ident():
            raise NestedUnitError

        self.lock.acquire()
        if self.is_closed:
            self.lock.release()
            raise DatabaseClosedError

        self.holder = get_ident()

    def release(self) -> None:
        self.holder = None
        self.lock.release()

    def close(self) -> None:
        if not self.lock.acquire(blocking=False):
            raise DatabaseInUseError

        try:
            self.is_closed = True
            with translate_errors('close'):
                self.connection.close()
        finally:
            self.lock.release()


@dataclass(slots=True, kw_only=True, frozen=True)
class UnitKind:
    begin: str
    is_read_only: bool
    errors: SqliteErrorTranslator


READ_UNIT = UnitKind(
    begin='BEGIN DEFERRED', is_read_only=True, errors=SqliteErrorTranslator.for_read_unit()
)
WRITE_UNIT = UnitKind(
    begin='BEGIN IMMEDIATE', is_read_only=False, errors=SqliteErrorTranslator.for_database()
)


@runtime_checkable
class Unit(Protocol):
    def one[P: Struct, R: Struct](self, query: Query[P, R], params: P) -> R | None: ...

    def all[P: Struct, R: Struct](self, query: Query[P, R], params: P) -> list[R]: ...

    def run[P: Struct](self, command: Command[P], params: P) -> int: ...

    def run_many[P: Struct](self, command: Command[P], batch: Iterable[P]) -> int: ...


@dataclass(slots=True, kw_only=True)
class SqliteUnit:
    channel: Channel
    errors: SqliteErrorTranslator
    is_active: bool = True

    def sql_for(self, declaration: Declaration) -> str:
        if not self.is_active:
            raise UnitExitedError

        return self.channel.catalogue.sql_for(declaration)

    def fetch_rows[P: Struct, R: Struct](self, query: Query[P, R], params: P) -> list[str]:
        sql = self.sql_for(query)
        bound = bind_params(params)
        with self.errors.translate(query.name):
            cursor = self.channel.connection.execute(sql, bound)
            return [row[0] for row in cursor.fetchall()]

    def one[P: Struct, R: Struct](self, query: Query[P, R], params: P) -> R | None:
        rows = self.fetch_rows(query, params)
        return decode_row(query, rows[0]) if rows else None

    def all[P: Struct, R: Struct](self, query: Query[P, R], params: P) -> list[R]:
        return decode_rows(query, self.fetch_rows(query, params))

    def run[P: Struct](self, command: Command[P], params: P) -> int:
        sql = self.sql_for(command)
        bound = bind_params(params)
        with self.errors.translate(command.name):
            return self.channel.connection.execute(sql, bound).rowcount

    def run_many[P: Struct](self, command: Command[P], batch: Iterable[P]) -> int:
        sql = self.sql_for(command)
        bound = [bind_params(params) for params in batch]
        with self.errors.translate(command.name):
            return self.channel.connection.executemany(sql, bound).rowcount


@dataclass(slots=True, kw_only=True)
class UnitScope:
    channel: Channel
    kind: UnitKind
    is_spent: bool = False
    unit: SqliteUnit | None = None

    def __enter__(self) -> Unit:
        if self.is_spent:
            raise UnitReusedError

        self.is_spent = True
        self.channel.claim()
        try:
            self.begin()
        except BaseException:
            self.release()
            raise

        self.unit = SqliteUnit(channel=self.channel, errors=self.kind.errors)
        return self.unit

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.unit is not None:
            self.unit.is_active = False

        try:
            if exc_type is not None:
                self.rollback()
                return

            self.commit()
        finally:
            self.release()

    def run_sql(self, sql: str) -> None:
        with self.kind.errors.translate(sql):
            self.channel.connection.execute(sql)

    def begin(self) -> None:
        if self.kind.is_read_only:
            self.run_sql('PRAGMA query_only = ON')

        self.run_sql(self.kind.begin)

    def rollback(self) -> None:
        if self.channel.connection.in_transaction:
            self.run_sql('ROLLBACK')

    def commit(self) -> None:
        try:
            self.run_sql('COMMIT')
        except DatabaseError:
            self.rollback()
            raise

    def end_read_only(self) -> None:
        try:
            self.rollback()
        finally:
            self.run_sql('PRAGMA query_only = OFF')

    def release(self) -> None:
        try:
            if self.kind.is_read_only:
                self.end_read_only()
        finally:
            self.channel.release()
