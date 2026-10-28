"""Where `verify run` keeps and finds its state: the data directory, the toplevel, the contract."""

import shlex
import sys
from typing import TYPE_CHECKING

import pytest
from mightymodels_cli.main import main
from mightymodels_core.edge import DATABASE_NAME, SESSION_DATA_VARIABLE, export_line
from mightymodels_core.workspace import STATE_DIRECTORY

from tests.cli.integration.verify_builders import (
    PASSED,
    REFUSED,
    VERIFY_RUN,
    sqlite_files_below,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tests.cli.integration.verify_builders import ApprovedContract

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures('session_data_directory', 'clean_git_environment'),
]

PASSED_RECEIPT = ['I1 at-head pass']
ALLOWED_KEY = 'T1.AC-1'
MARKER = 'ran.txt'
TOUCH = f'import sys; from pathlib import Path; Path({MARKER!r}).write_text(" ".join(sys.argv[1:]))'


class TestTheDatabaseFile:
    @pytest.mark.usefixtures('session_in_the_repository')
    def test_verify_run_creates_it_in_the_data_directory_and_none_in_the_repository(
        self, repository: Path, session_data_directory: Path
    ) -> None:
        main(VERIFY_RUN)

        assert sqlite_files_below(session_data_directory) == [DATABASE_NAME]
        assert sqlite_files_below(repository) == []

    @pytest.mark.usefixtures('session_in_the_repository')
    def test_verify_run_opens_the_database_a_core_service_wrote(
        self, contract: ApprovedContract, capsys: pytest.CaptureFixture[str]
    ) -> None:
        contract.approve()

        code = main(VERIFY_RUN)

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')
        assert contract.receipts() == PASSED_RECEIPT


class TestStartingInASubdirectory:
    @pytest.mark.usefixtures('session_in_the_subdirectory')
    def test_verify_run_finds_the_toplevel_and_the_contract_approved_there(
        self,
        contract: ApprovedContract,
        subdirectory: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        contract.approve()

        code = main(VERIFY_RUN)

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')
        assert not subdirectory.joinpath(STATE_DIRECTORY).exists()


class TestTheRunReceipt:
    @pytest.mark.usefixtures('session_in_the_repository')
    def test_the_approved_command_runs_and_its_receipt_shows_in_the_status(
        self, contract: ApprovedContract
    ) -> None:
        contract.approve()

        main(VERIFY_RUN)

        assert contract.receipts() == PASSED_RECEIPT


class TestWithWhatTheSessionStartHookExported:
    @pytest.fixture
    def session_after_the_hook(
        self,
        session_data_directory: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, assignment = shlex.split(export_line(session_data_directory))
        name, _, value = assignment.partition('=')
        monkeypatch.delenv(SESSION_DATA_VARIABLE)
        monkeypatch.setenv(name, value)

    @pytest.mark.usefixtures('session_in_the_repository', 'session_after_the_hook')
    def test_verify_run_opens_the_database_a_core_service_wrote(
        self, contract: ApprovedContract, capsys: pytest.CaptureFixture[str]
    ) -> None:
        contract.approve()

        code = main(VERIFY_RUN)

        assert code == PASSED
        assert capsys.readouterr().out.startswith('I1 pass ')
        assert contract.receipts() == PASSED_RECEIPT


class TestTheAllowlist:
    @pytest.mark.usefixtures('session_in_the_repository')
    def test_verify_run_takes_ids_and_never_a_command_line(
        self, contract: ApprovedContract, repository: Path
    ) -> None:
        contract.approve((sys.executable, '-c', 'print(1)'), key=ALLOWED_KEY)
        trailing = [sys.executable, '-c', TOUCH]

        with pytest.raises(SystemExit) as exit_info:
            main(['verify', 'run', '--slug', 'port-cli', '--id', ALLOWED_KEY, '--', *trailing])

        assert exit_info.value.code == REFUSED
        assert not repository.joinpath(MARKER).exists()
        assert contract.receipts() == [f'{ALLOWED_KEY} never-run None']
