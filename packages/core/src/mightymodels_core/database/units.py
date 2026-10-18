"""Single-use read and write units of work over the one connection a database owns.

A unit holds the database's lock from entry to exit, so units from different threads run one
at a time. COMMIT and ROLLBACK run as SQL because the connection stays in autocommit mode.
"""

from dataclasses import dataclass, field
from threading import Lock, get_ident
from typing import TYPE_CHECKING

from msgspec import Struct

from .codec import bind_params, decode_row, decode_rows
from .errors import (
    DatabaseClosedError,
    DatabaseError,
    NestedUnitError,
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


@dataclass(slots=True, kw_only=True, frozen=True)
class UnitKind:
    begin: str
    is_read_only: bool


READ_UNIT = UnitKind(begin='BEGIN DEFERRED', is_read_only=True)
WRITE_UNIT = UnitKind(begin='BEGIN IMMEDIATE', is_read_only=False)


@dataclass(slots=True, kw_only=True)
class Unit:
    channel: Channel
    is_active: bool = True

    def execute(self, declaration: Declaration, params: Struct) -> sqlite3.Cursor:
        if not self.is_active:
            raise UnitExitedError

        sql = self.channel.catalogue.sql_for(declaration)
        bound = bind_params(params)
        with translate_errors(declaration.name):
            return self.channel.connection.execute(sql, bound)

    def fetch_rows[P: Struct, R: Struct](self, query: Query[P, R], params: P) -> list[str]:
        cursor = self.execute(query, params)
        with translate_errors(query.name):
            return [row[0] for row in cursor.fetchall()]

    def one[P: Struct, R: Struct](self, query: Query[P, R], params: P) -> R | None:
        rows = self.fetch_rows(query, params)
        return decode_row(query, rows[0]) if rows else None

    def all[P: Struct, R: Struct](self, query: Query[P, R], params: P) -> list[R]:
        return decode_rows(query, self.fetch_rows(query, params))

    def run[P: Struct](self, command: Command[P], params: P) -> int:
        return self.execute(command, params).rowcount

    def run_many[P: Struct](self, command: Command[P], batch: Iterable[P]) -> int:
        if not self.is_active:
            raise UnitExitedError

        sql = self.channel.catalogue.sql_for(command)
        bound = [bind_params(params) for params in batch]
        with translate_errors(command.name):
            return self.channel.connection.executemany(sql, bound).rowcount


@dataclass(slots=True, kw_only=True)
class UnitScope:
    channel: Channel
    kind: UnitKind
    is_spent: bool = False
    unit: Unit | None = None

    def __enter__(self) -> Unit:
        if self.is_spent:
            raise UnitReusedError

        self.is_spent = True
        if self.channel.holder == get_ident():
            raise NestedUnitError

        self.channel.lock.acquire()
        if self.channel.is_closed:
            self.channel.lock.release()
            raise DatabaseClosedError

        self.channel.holder = get_ident()
        try:
            self.begin()
        except BaseException:
            self.release()
            raise

        self.unit = Unit(channel=self.channel)
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
            self.finish(commit=exc_type is None)
        finally:
            self.release()

    def run_sql(self, sql: str) -> None:
        with translate_errors(sql):
            self.channel.connection.execute(sql)

    def begin(self) -> None:
        if self.kind.is_read_only:
            self.run_sql('PRAGMA query_only = ON')

        self.run_sql(self.kind.begin)

    def rollback(self) -> None:
        if self.channel.connection.in_transaction:
            self.run_sql('ROLLBACK')

    def finish(self, *, commit: bool) -> None:
        if not commit:
            self.rollback()
            return

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
            self.channel.holder = None
            self.channel.lock.release()
