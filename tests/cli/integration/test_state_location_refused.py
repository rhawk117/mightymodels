"""What `verify run` refuses to start on: exit 2, the reason on standard error, nothing created."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_cli.main import main
from mightymodels_core.edge import DATABASE_NAME, SESSION_DATA_VARIABLE
from mightymodels_core.workspace import PROJECT_DIR_VARIABLE, STATE_DIRECTORY

from tests.cli.integration.verify_builders import (
    OLD_TABLES,
    REFUSED,
    SLUG,
    VERIFY_RUN,
    kept,
    refused_start,
    sqlite_file,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tests.cli.integration.verify_builders import ApprovedContract, KeptFile, RefusedStart

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures('session_data_directory', 'clean_git_environment'),
]

ANOTHER_VERSION = 99
NOT_SET = 'is not set'
NOT_A_REPOSITORY = 'is not inside a git repository'
NEEDS_GIT = 'this needs git and no git executable is on PATH'
MISMATCHES = (
    pytest.param((f'PRAGMA user_version = {ANOTHER_VERSION}',), ANOTHER_VERSION, id='another'),
    pytest.param(OLD_TABLES, 0, id='unstamped-with-tables'),
    pytest.param(
        ('PRAGMA journal_mode = WAL', f'PRAGMA user_version = {ANOTHER_VERSION}'),
        ANOTHER_VERSION,
        id='another-in-write-ahead-log-mode',
    ),
)


@pytest.mark.usefixtures('session_in_the_repository')
class TestAnOldDatabaseInTheRepository:
    def test_verify_run_does_not_read_its_rows_and_leaves_it_as_it_was(
        self, repository: Path, contract: ApprovedContract, capsys: pytest.CaptureFixture[str]
    ) -> None:
        contract.stage()
        old_database = kept(
            sqlite_file(repository.joinpath(STATE_DIRECTORY, DATABASE_NAME), OLD_TABLES)
        )

        code = main(VERIFY_RUN)

        assert code == REFUSED
        assert f'{SLUG} has no approved commands' in capsys.readouterr().err
        assert old_database.is_as_it_was()


@pytest.mark.usefixtures('session_in_the_repository')
class TestASchemaVersionMismatch:
    @pytest.fixture
    def mismatched(self, request: pytest.FixtureRequest, session_data_directory: Path) -> KeptFile:
        return kept(sqlite_file(session_data_directory.joinpath(DATABASE_NAME), request.param))

    @pytest.mark.parametrize(('mismatched', 'found'), MISMATCHES, indirect=['mismatched'])
    def test_verify_run_refuses_on_standard_error_naming_the_version_found(
        self, mismatched: KeptFile, found: int, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == REFUSED
        assert f'the file is at schema version {found}' in capsys.readouterr().err
        assert mismatched.has_nothing_beside_it()
        assert mismatched.is_as_it_was()


class TestWithNoDataDirectory:
    @pytest.fixture
    def session_without_the_export(
        self, session_in_the_repository: Path, monkeypatch: pytest.MonkeyPatch
    ) -> RefusedStart:
        monkeypatch.delenv(SESSION_DATA_VARIABLE)
        return refused_start(session_in_the_repository.parent)

    def test_verify_run_refuses_on_standard_error_naming_the_variable(
        self, session_without_the_export: RefusedStart, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == REFUSED
        assert f'error: {SESSION_DATA_VARIABLE} {NOT_SET}' in capsys.readouterr().err
        assert session_without_the_export.created_nothing()


class TestWithNoGitToplevel:
    @pytest.fixture
    def outside_a_repository(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        monkeypatch.setenv(PROJECT_DIR_VARIABLE, str(directory))
        return directory

    @pytest.fixture
    def without_git(
        self, session_in_the_repository: Path, monkeypatch: pytest.MonkeyPatch
    ) -> RefusedStart:
        top = session_in_the_repository.parent
        monkeypatch.setenv('PATH', str(top.joinpath('no-binaries')))
        return refused_start(top)

    def test_outside_a_repository_verify_run_refuses_naming_the_directory(
        self,
        outside_a_repository: Path,
        session_data_directory: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        before = refused_start(outside_a_repository.parent)

        code = main(VERIFY_RUN)

        assert code == REFUSED
        assert f'{outside_a_repository} {NOT_A_REPOSITORY}' in capsys.readouterr().err
        assert before.created_nothing()
        assert not session_data_directory.exists()

    def test_without_git_verify_run_refuses_naming_git(
        self, without_git: RefusedStart, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(VERIFY_RUN)

        assert code == REFUSED
        assert f'error: {NEEDS_GIT}' in capsys.readouterr().err
        assert without_git.created_nothing()
