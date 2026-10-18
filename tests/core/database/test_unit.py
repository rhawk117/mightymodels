from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from operator import methodcaller
from threading import Event
from typing import TYPE_CHECKING, Any

import pytest
from mightymodels_core.database import (
    BusyError,
    ConnectionOptions,
    DuplicateRowError,
    MissingParentError,
    NestedUnitError,
    ReadOnlyUnitError,
    RejectedValueError,
    StatementFailedError,
    UnitExitedError,
    UnitReusedError,
    UnknownStatementError,
    open_database,
)

from .conftest import NamePart, NoPart, PersonPart, PersonRow, create_statements

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future
    from pathlib import Path

    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Command, Database, DatabaseSpec, UnitScope
    from mightymodels_core.database.errors import SqliteFailure
    from msgspec import Struct

    from .conftest import Statements

pytestmark = pytest.mark.integration

STATEMENTS = create_statements()
ADA = PersonPart(name='ada', age=36)
GRACE = PersonPart(name='grace', age=45)


class RollbackTriggerError(Exception):
    pass


@dataclass(slots=True, kw_only=True, frozen=True)
class FailingStatement:
    name: str
    command: Command[Any]
    params: Struct
    error_type: type[SqliteFailure]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def failing_statement_cases() -> pytest.MarkDecorator:
    cases = [
        FailingStatement(
            name='duplicate',
            command=STATEMENTS.add_person,
            params=ADA,
            error_type=DuplicateRowError,
        ),
        FailingStatement(
            name='missing-parent',
            command=STATEMENTS.add_person,
            params=PersonPart(name='linus', team_id=99),
            error_type=MissingParentError,
        ),
        FailingStatement(
            name='check',
            command=STATEMENTS.add_person,
            params=PersonPart(name='linus', age=-1),
            error_type=RejectedValueError,
        ),
        FailingStatement(
            name='not-null',
            command=STATEMENTS.add_nameless_person,
            params=NoPart(),
            error_type=RejectedValueError,
        ),
        FailingStatement(
            name='other-sqlite-error',
            command=STATEMENTS.delete_from_missing_table,
            params=NoPart(),
            error_type=StatementFailedError,
        ),
    ]
    return pytest.mark.parametrize('failing', [case.param for case in cases])


@dataclass(slots=True, kw_only=True, frozen=True)
class Opener:
    name: str
    outer: Callable[[Database], UnitScope]
    inner: Callable[[Database], UnitScope]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def nested_unit_cases() -> pytest.MarkDecorator:
    read, write = methodcaller('read'), methodcaller('write')
    cases = [
        Opener(name='read-in-read', outer=read, inner=read),
        Opener(name='write-in-read', outer=read, inner=write),
        Opener(name='read-in-write', outer=write, inner=read),
        Opener(name='write-in-write', outer=write, inner=write),
    ]
    return pytest.mark.parametrize('opener', [case.param for case in cases])


def write_then_fail(database: Database, statements: Statements) -> None:
    with database.write() as unit:
        unit.run(statements.add_person, ADA)
        raise RollbackTriggerError


def count_people(database: Database, statements: Statements) -> int:
    with database.read() as unit:
        return len(unit.all(statements.all_people, NoPart()))


class TestWriteUnit:
    def test_clean_exit_commits(self, database: Database, statements: Statements) -> None:
        with database.write() as unit:
            unit.run(statements.add_person, ADA)
        with database.read() as unit:
            found = unit.one(statements.find_person, NamePart(name='ada'))
        assert found == PersonRow(name='ada', age=36)

    def test_exception_rolls_back_and_reraises(
        self, database: Database, statements: Statements
    ) -> None:
        with pytest.raises(RollbackTriggerError):
            write_then_fail(database, statements)
        assert count_people(database, statements) == 0

    def test_run_many_returns_the_total_rowcount(
        self, database: Database, statements: Statements
    ) -> None:
        with database.write() as unit:
            added = unit.run_many(statements.add_person, [ADA, GRACE])
            everyone = unit.all(statements.all_people, NoPart())
        assert added == 2
        assert [person.name for person in everyone] == ['ada', 'grace']

    def test_one_returns_none_for_no_row(self, database: Database, statements: Statements) -> None:
        with database.read() as unit:
            assert unit.one(statements.find_person, NamePart(name='nobody')) is None

    @failing_statement_cases()
    def test_sqlite_failure_reaches_the_caller_as_a_domain_error(
        self,
        database: Database,
        statements: Statements,
        failing: FailingStatement,
    ) -> None:
        with database.write() as unit:
            unit.run(statements.add_person, ADA)
        with pytest.raises(failing.error_type) as raised, database.write() as unit:
            unit.run(failing.command, failing.params)
        assert raised.value.statement == failing.command.name
        assert raised.value.detail

    def test_undeclared_statement_is_a_misuse_error(
        self, database: Database, rename: Command[NamePart]
    ) -> None:
        with database.write() as unit, pytest.raises(UnknownStatementError) as raised:
            unit.run(rename, NamePart(name='ada'))
        assert raised.value.name == 'rename'


class TestReadUnit:
    def test_write_in_a_read_unit_raises_and_stores_nothing(
        self, database: Database, statements: Statements
    ) -> None:
        with pytest.raises(ReadOnlyUnitError), database.read() as unit:
            unit.run(statements.add_person, ADA)
        assert count_people(database, statements) == 0

    def test_a_write_unit_works_after_a_read_unit(
        self, database: Database, statements: Statements
    ) -> None:
        count_people(database, statements)
        with database.write() as unit:
            assert unit.run(statements.add_person, ADA) == 1


class TestUnitLifecycle:
    def test_call_on_an_exited_unit_raises(
        self, database: Database, statements: Statements
    ) -> None:
        with database.read() as unit:
            pass
        with pytest.raises(UnitExitedError):
            unit.all(statements.all_people, NoPart())

    def test_unit_scope_is_single_use(self, database: Database) -> None:
        scope = database.read()
        with scope:
            pass
        with pytest.raises(UnitReusedError):
            scope.__enter__()

    @nested_unit_cases()
    def test_nested_unit_raises(
        self, database: Database, statements: Statements, opener: Opener
    ) -> None:
        with opener.outer(database), pytest.raises(NestedUnitError):
            opener.inner(database).__enter__()
        assert count_people(database, statements) == 0


class TestConcurrency:
    def hold_while_second_waits(
        self,
        database: Database,
        statements: Statements,
        pool: ThreadPoolExecutor,
        second: Callable[[], None],
        second_entered: Event,
    ) -> Future[None]:
        with database.write() as unit:
            unit.run(statements.add_person, ADA)
            waiting = pool.submit(second)
            assert not second_entered.wait(timeout=0.2)
        return waiting

    def test_contended_write_raises_busy_after_the_timeout(
        self,
        database: Database,
        database_path: Path,
        database_spec: DatabaseSpec,
        statements: Statements,
    ) -> None:
        options = ConnectionOptions(busy_timeout_seconds=0.05)
        with (
            closing(open_database(database_path, database_spec, options)) as contender,
            database.write(),
            pytest.raises(BusyError),
            contender.write() as unit,
        ):
            unit.run(statements.add_person, ADA)
        assert count_people(database, statements) == 0

    def test_units_from_two_threads_run_one_at_a_time(
        self, database: Database, statements: Statements
    ) -> None:
        second_entered = Event()

        def write_second() -> None:
            with database.write() as unit:
                second_entered.set()
                unit.run(statements.add_person, GRACE)

        with ThreadPoolExecutor(max_workers=1) as pool:
            waiting = self.hold_while_second_waits(
                database, statements, pool, write_second, second_entered
            )
            waiting.result(timeout=5)
        assert second_entered.is_set()
        assert count_people(database, statements) == 2
