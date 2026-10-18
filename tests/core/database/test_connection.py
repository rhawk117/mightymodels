from contextlib import closing
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import (
    ConnectionOptions,
    DatabaseClosedError,
    DatabaseInUseError,
    DatabaseSpec,
    JournalMode,
    SchemaVersionError,
    StatementFailedError,
    UnversionedSchemaError,
    open_database,
)

from .conftest import FIXTURE_VERSION, NamePart, NoPart, PersonPart

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.database import Database

    from .conftest import Statements

pytestmark = pytest.mark.integration


class TestOpen:
    def test_foreign_keys_are_enforced(self, database: Database, statements: Statements) -> None:
        with database.read() as unit:
            row = unit.one(statements.foreign_keys, NoPart())
        assert row is not None
        assert row.value == 1

    def test_journal_mode_is_wal(self, database: Database, statements: Statements) -> None:
        with database.read() as unit:
            row = unit.one(statements.journal_mode, NoPart())
        assert row is not None
        assert row.value == 'wal'

    def test_options_override_the_defaults(
        self, database_path: Path, database_spec: DatabaseSpec, statements: Statements
    ) -> None:
        options = ConnectionOptions(foreign_keys=False, journal_mode=JournalMode.DELETE)
        with (
            closing(open_database(database_path, database_spec, options)) as opened,
            opened.read() as unit,
        ):
            foreign_keys = unit.one(statements.foreign_keys, NoPart())
            journal_mode = unit.one(statements.journal_mode, NoPart())
        assert foreign_keys is not None
        assert foreign_keys.value == 0
        assert journal_mode is not None
        assert journal_mode.value == 'delete'

    def test_fresh_file_gets_the_schema_and_its_version(
        self, database: Database, statements: Statements
    ) -> None:
        with database.write() as unit:
            added = unit.run(statements.add_person, PersonPart(name='ada'))
        with database.read() as unit:
            version = unit.one(statements.user_version, NoPart())
        assert added == 1
        assert version is not None
        assert version.value == FIXTURE_VERSION

    def test_reopening_keeps_the_stored_rows(
        self, database_path: Path, database_spec: DatabaseSpec, statements: Statements
    ) -> None:
        with (
            closing(open_database(database_path, database_spec, ConnectionOptions())) as first,
            first.write() as unit,
        ):
            unit.run(statements.add_person, PersonPart(name='ada'))
        with (
            closing(open_database(database_path, database_spec, ConnectionOptions())) as second,
            second.read() as unit,
        ):
            found = unit.one(statements.find_person, NamePart(name='ada'))
        assert found is not None
        assert found.name == 'ada'

    @pytest.mark.usefixtures('database')
    def test_different_version_refuses_to_open(
        self, database_path: Path, tmp_path: Path, statements: Statements
    ) -> None:
        newer = tmp_path.joinpath('newer.sql')
        newer.write_text('CREATE TABLE extra (id INTEGER PRIMARY KEY);\nPRAGMA user_version = 8;')
        spec = DatabaseSpec(
            schema=newer,
            statements=tmp_path.joinpath('statements.sql'),
            declarations=statements.declarations,
        )
        with pytest.raises(SchemaVersionError) as refused:
            open_database(database_path, spec, ConnectionOptions())
        assert (refused.value.found, refused.value.expected) == (FIXTURE_VERSION, 8)

    def test_schema_without_a_version_refuses_to_open(
        self, database_path: Path, database_spec: DatabaseSpec, tmp_path: Path
    ) -> None:
        unversioned = tmp_path.joinpath('unversioned.sql')
        unversioned.write_text('CREATE TABLE extra (id INTEGER PRIMARY KEY);')
        spec = DatabaseSpec(
            schema=unversioned,
            statements=database_spec.statements,
            declarations=database_spec.declarations,
        )
        with pytest.raises(UnversionedSchemaError):
            open_database(database_path, spec, ConnectionOptions())
        assert not database_path.exists()

    def test_sqlite_open_failure_is_a_domain_error(
        self, tmp_path: Path, database_spec: DatabaseSpec
    ) -> None:
        missing_directory = tmp_path.joinpath('missing', 'fixture.db')
        with pytest.raises(StatementFailedError) as failed:
            open_database(missing_directory, database_spec, ConnectionOptions())
        assert failed.value.statement == 'open'


class TestClose:
    def test_closing_context_closes_the_database(
        self, database_path: Path, database_spec: DatabaseSpec
    ) -> None:
        with closing(open_database(database_path, database_spec, ConnectionOptions())) as opened:
            pass
        with pytest.raises(DatabaseClosedError):
            opened.read().__enter__()

    def test_close_with_a_unit_open_raises_and_closes_nothing(
        self, database: Database, statements: Statements
    ) -> None:
        with database.write() as unit:
            with pytest.raises(DatabaseInUseError):
                database.close()
            added = unit.run(statements.add_team, NamePart(name='core'))
        assert added == 1
