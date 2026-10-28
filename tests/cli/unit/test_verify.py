from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_cli.main import main
from mightymodels_cli.verify import receipt_text
from mightymodels_core.contract import Receipt
from mightymodels_core.primitives import redact

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.vocabulary.contract import Outcome

pytestmark = pytest.mark.unit

SLUG = 'port-cli'
RUN_ARGUMENTS = ['verify', 'run', '--slug', SLUG, '--all']


def create_receipt(
    *, outcome: Outcome, exit_code: int | None, stdout: str = '', stderr: str = ''
) -> Receipt:
    return Receipt(
        key='I1',
        argv=('true',),
        outcome=outcome,
        exit=exit_code,
        duration_ms=1250,
        stdout_tail=redact(stdout),
        stderr_tail=redact(stderr),
        digest='0' * 64,
        head='abc1234',
        phase='task',
        at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class TestReceiptText:
    def test_a_pass_is_one_line(self) -> None:
        receipt = create_receipt(outcome='pass', exit_code=0, stdout='ignored\n')

        assert receipt_text(receipt) == 'I1 pass exit=0 1.2s\n'

    def test_a_failure_lists_the_stderr_tail(self) -> None:
        receipt = create_receipt(outcome='fail', exit_code=1, stdout='out\n', stderr='a\nb\n')

        assert receipt_text(receipt) == 'I1 fail exit=1 1.2s\n  | a\n  | b\n'

    def test_a_failure_without_stderr_lists_the_stdout_tail(self) -> None:
        receipt = create_receipt(outcome='fail', exit_code=1, stdout='out\n')

        assert receipt_text(receipt) == 'I1 fail exit=1 1.2s\n  | out\n'

    def test_a_run_with_no_exit_code_shows_none(self) -> None:
        receipt = create_receipt(outcome='timeout', exit_code=None, stderr='too slow')

        assert receipt_text(receipt) == 'I1 timeout exit=None 1.2s\n  | too slow\n'


class TestRefusals:
    def test_an_invalid_slug_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(['verify', 'run', '--slug', '../escape', '--all']) == 2

        assert capsys.readouterr().err.startswith('error: ')

    @pytest.mark.usefixtures('no_session_data_directory')
    def test_a_missing_data_directory_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(RUN_ARGUMENTS) == 2

        assert 'MIGHTYMODELS_DATA_DIR' in capsys.readouterr().err

    @pytest.mark.usefixtures('project_outside_a_repository')
    def test_a_start_outside_a_repository_is_refused(
        self, session_data_directory: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(RUN_ARGUMENTS) == 2

        assert capsys.readouterr().err.startswith('error: ')
        assert not session_data_directory.exists()
