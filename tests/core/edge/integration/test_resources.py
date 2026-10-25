import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import DatabaseClosedError, SchemaVersionError, open_database
from mightymodels_core.edge import (
    DATABASE_NAME,
    DataDirectoryMissingError,
    open_state,
)
from mightymodels_core.git import GitMissingError, NotARepositoryError
from mightymodels_core.workspace import EXCLUDE_LINE

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from mightymodels_core.database import Database, DatabaseSpec
    from mightymodels_core.edge import OpenState
    from mightymodels_core.git import Git

    from tests.core.checkout_builders import StartHarness


def exclude_lines(start: StartHarness) -> list[str]:
    exclude = start.toplevel.joinpath('.git', 'info', 'exclude')
    return exclude.read_text(encoding='utf-8').splitlines() if exclude.is_file() else []


class TestOpenStateRefused:
    async def test_a_missing_data_directory_raises_data_directory_missing_error(
        self, start: StartHarness
    ) -> None:
        missing = DataDirectoryMissingError(variable='CLAUDE_PLUGIN_DATA', session_variable='X')

        with pytest.raises(DataDirectoryMissingError) as refusal:
            async with open_state(missing, start.toplevel):
                pass

        assert refusal.value is missing
        assert not start.data_directory.exists()
        assert EXCLUDE_LINE not in exclude_lines(start)

    async def test_a_start_outside_a_work_tree_is_refused_before_anything_is_created(
        self, start: StartHarness
    ) -> None:
        with pytest.raises(NotARepositoryError):
            async with open_state(start.data_directory, start.outside):
                pass

        assert not start.data_directory.exists()

    async def test_without_git_the_refusal_is_raised_before_anything_is_created(
        self, start: StartHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('PATH', str(start.outside))

        with pytest.raises(GitMissingError):
            async with open_state(start.data_directory, start.toplevel):
                pass

        assert not start.data_directory.exists()

    async def test_a_database_of_another_schema_version_is_refused_and_nothing_is_excluded(
        self, start: StartHarness
    ) -> None:
        start.data_directory.mkdir(parents=True)
        other = start.data_directory.joinpath(DATABASE_NAME)
        with sqlite3.connect(other) as connection:
            connection.execute('PRAGMA user_version = 9999')
        connection.close()

        with pytest.raises(SchemaVersionError) as refusal:
            async with open_state(start.data_directory, start.toplevel):
                pass

        assert refusal.value.found == 9999
        assert EXCLUDE_LINE not in exclude_lines(start)


class TestOpenState:
    @pytest.fixture
    async def opened(self, start: StartHarness) -> AsyncGenerator[OpenState]:
        async with open_state(start.data_directory, start.subdirectory) as state:
            yield state

    async def test_the_checkout_is_the_toplevel_whatever_directory_it_starts_in(
        self, opened: OpenState, start: StartHarness
    ) -> None:
        assert opened.checkout.toplevel == start.toplevel

    async def test_the_database_is_opened_in_the_data_directory(
        self, opened: OpenState, start: StartHarness
    ) -> None:
        assert start.data_directory.joinpath(DATABASE_NAME).is_file()
        assert opened.database is not None

    @pytest.mark.usefixtures('opened')
    async def test_the_state_directory_is_excluded_from_git(self, start: StartHarness) -> None:
        assert exclude_lines(start).count(EXCLUDE_LINE) == 1

    async def test_the_git_answers_at_the_toplevel(
        self, opened: OpenState, start: StartHarness
    ) -> None:
        common_directory = await opened.git.common_directory()

        assert common_directory == start.toplevel.joinpath('.git')

    async def test_a_second_start_opens_the_same_file_and_excludes_once(
        self, opened: OpenState, start: StartHarness
    ) -> None:
        async with open_state(start.data_directory, start.toplevel) as again:
            assert opened.checkout == again.checkout

        assert exclude_lines(start).count(EXCLUDE_LINE) == 1


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusingBackends:
    refusal: PermissionError
    opened: list[Database] = field(default_factory=list)

    def connect(self, path: Path, spec: DatabaseSpec) -> Database:
        database = open_database(path, spec)
        self.opened.append(database)
        return database

    async def exclude(self, _git: Git, /) -> None:
        raise self.refusal


class TestOpenStateCloses:
    refusal = PermissionError('exclude refused')

    @pytest.fixture
    def refusing_backends(self) -> RefusingBackends:
        return RefusingBackends(refusal=self.refusal)

    def assert_closed(self, database: Database) -> None:
        with pytest.raises(DatabaseClosedError), database.read():
            pass

    async def test_the_database_is_closed_after_the_block_exits(self, start: StartHarness) -> None:
        async with open_state(start.data_directory, start.toplevel) as state:
            with state.database.read():
                pass

        self.assert_closed(state.database)

    async def test_the_database_is_closed_when_excluding_the_state_raises(
        self, start: StartHarness, refusing_backends: RefusingBackends
    ) -> None:
        with pytest.raises(PermissionError) as raised:
            async with open_state(start.data_directory, start.toplevel, backends=refusing_backends):
                pass

        assert raised.value is self.refusal
        (database,) = refusing_backends.opened
        self.assert_closed(database)
