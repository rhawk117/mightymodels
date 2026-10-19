"""Domain errors of the database adapter: one class per failure, none of them a `sqlite3` error."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from contextlib import AbstractContextManager


class DatabaseError(Exception):
    pass


class DuplicateBlockError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement block {name!r} appears more than once')


class EmptyBlockError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement block {name!r} holds no SQL')


class DuplicateDeclarationError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement {name!r} is declared more than once')


class MissingBlockError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement {name!r} is declared but has no block')


class UndeclaredBlockError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement block {name!r} has no declaration')


class NaiveTimestampError(DatabaseError):
    def __init__(self, *, field: str) -> None:
        self.field = field
        super().__init__(f'parameter {field!r} is a datetime without a timezone')


class RowDecodeError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} returned a row that does not decode: {detail}')


class DuplicateRowError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} duplicated a unique value: {detail}')


class MissingParentError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} references a row that does not exist: {detail}')


class RejectedValueError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} stored a value the table rejects: {detail}')


class BusyError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} found the database busy: {detail}')


class ReadOnlyUnitError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} wrote inside a read unit: {detail}')


class ReadOnlyDatabaseError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} wrote to a read-only database: {detail}')


class StatementFailedError(DatabaseError):
    def __init__(self, *, statement: str, detail: str) -> None:
        self.statement = statement
        self.detail = detail
        super().__init__(f'statement {statement!r} failed: {detail}')


class UnknownStatementError(DatabaseError):
    def __init__(self, *, name: str) -> None:
        self.name = name
        super().__init__(f'statement {name!r} is not in the open catalogue')


class UnitExitedError(DatabaseError):
    def __init__(self) -> None:
        super().__init__('the unit of work has exited and accepts no more statements')


class UnitReusedError(DatabaseError):
    def __init__(self) -> None:
        super().__init__('a unit of work is single-use and was already entered')


class NestedUnitError(DatabaseError):
    def __init__(self) -> None:
        super().__init__('a unit of work cannot open inside another unit of the same database')


class DatabaseInUseError(DatabaseError):
    def __init__(self) -> None:
        super().__init__('the database cannot close while a unit of work is open')


class DatabaseClosedError(DatabaseError):
    def __init__(self) -> None:
        super().__init__('the database is closed')


class UnversionedSchemaError(DatabaseError):
    def __init__(self) -> None:
        super().__init__('the schema script does not end with a PRAGMA user_version statement')


class PragmaNotAppliedError(DatabaseError):
    def __init__(self, *, pragma: str, expected: str, found: str) -> None:
        self.pragma = pragma
        self.expected = expected
        self.found = found
        super().__init__(f'PRAGMA {pragma} is {found}, the options ask for {expected}')


class SchemaVersionError(DatabaseError):
    def __init__(self, *, found: int, expected: int) -> None:
        self.found = found
        self.expected = expected
        super().__init__(f'the file is at schema version {found}, the schema script is {expected}')


type SqliteFailure = (
    DuplicateRowError
    | MissingParentError
    | RejectedValueError
    | BusyError
    | ReadOnlyDatabaseError
    | ReadOnlyUnitError
    | StatementFailedError
)

SQLITE_CONSTRAINT_DATATYPE = 3091


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteErrorTranslator:
    failure_by_name: Mapping[str, type[SqliteFailure]]
    failure_by_code: Mapping[int, type[SqliteFailure]]

    @classmethod
    def with_read_only(cls, read_only: type[SqliteFailure]) -> Self:
        by_name: dict[str, type[SqliteFailure]] = {
            'SQLITE_CONSTRAINT_UNIQUE': DuplicateRowError,
            'SQLITE_CONSTRAINT_PRIMARYKEY': DuplicateRowError,
            'SQLITE_CONSTRAINT_ROWID': DuplicateRowError,
            'SQLITE_CONSTRAINT_FOREIGNKEY': MissingParentError,
            'SQLITE_CONSTRAINT_CHECK': RejectedValueError,
            'SQLITE_CONSTRAINT_NOTNULL': RejectedValueError,
            'SQLITE_BUSY': BusyError,
            'SQLITE_READONLY': read_only,
        }
        by_code: dict[int, type[SqliteFailure]] = {SQLITE_CONSTRAINT_DATATYPE: RejectedValueError}
        return cls(
            failure_by_name=MappingProxyType(by_name),
            failure_by_code=MappingProxyType(by_code),
        )

    @classmethod
    def for_database(cls) -> Self:
        return cls.with_read_only(ReadOnlyDatabaseError)

    @classmethod
    def for_read_unit(cls) -> Self:
        return cls.with_read_only(ReadOnlyUnitError)

    def create_error(self, error: sqlite3.Error, *, statement: str) -> SqliteFailure:
        name = getattr(error, 'sqlite_errorname', '')
        primary = '_'.join(name.split('_')[:2])
        code = getattr(error, 'sqlite_errorcode', 0)
        failure = (
            self.failure_by_name.get(name)
            or self.failure_by_code.get(code)
            or self.failure_by_name.get(primary)
            or StatementFailedError
        )
        return failure(statement=statement, detail=str(error))

    @contextmanager
    def translate(self, statement: str) -> Generator[None]:
        try:
            yield
        except sqlite3.Error as error:
            raise self.create_error(error, statement=statement) from error


DATABASE_ERRORS = SqliteErrorTranslator.for_database()


def translate_errors(statement: str) -> AbstractContextManager[None]:
    return DATABASE_ERRORS.translate(statement)
