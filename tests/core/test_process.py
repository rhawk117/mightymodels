import contextlib
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from mightymodels_core.process import CompletedRun, FailedRun, SubprocessRunner

pytestmark = pytest.mark.integration


@dataclass(slots=True, kw_only=True, frozen=True)
class ChildPython:
    script: str

    @property
    def argv(self) -> list[str]:
        return [sys.executable, '-c', self.script]


def process_with_argument_runs(argument: str) -> bool:
    # The argv is fixed at exec, so this finds the child however late its own code starts.
    needle = argument.encode()
    for cmdline in Path('/proc').glob('[0-9]*/cmdline'):
        with contextlib.suppress(OSError):
            if needle in cmdline.read_bytes().split(b'\0'):
                return True
    return False


def is_same_directory(printed: str, expected: Path) -> bool:
    return Path(printed.strip()).resolve() == expected.resolve()


class TestSubprocessRunner:
    runner = SubprocessRunner()
    timeout = 1

    async def test_completed_run_carries_exit_and_both_streams(self) -> None:
        child = ChildPython(
            script='import sys; print("out"); print("err", file=sys.stderr); sys.exit(3)'
        )

        outcome = await self.runner.run(child.argv, timeout=30)

        assert outcome == CompletedRun(exit=3, stdout='out\n', stderr='err\n')

    async def test_working_directory_is_applied(self, tmp_path: Path) -> None:
        child = ChildPython(script='import os; print(os.getcwd())')

        outcome = await self.runner.run(child.argv, timeout=30, cwd=tmp_path)

        assert isinstance(outcome, CompletedRun)
        assert is_same_directory(outcome.stdout, tmp_path)

    async def test_missing_executable_is_not_found(self, tmp_path: Path) -> None:
        missing = tmp_path.joinpath('no-such-program')

        outcome = await self.runner.run([str(missing)], timeout=30)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'not_found'
        assert outcome.detail

    async def test_missing_working_directory_is_refused(self, tmp_path: Path) -> None:
        child = ChildPython(script='pass')
        missing = tmp_path.joinpath('no-such-directory')

        outcome = await self.runner.run(child.argv, timeout=30, cwd=missing)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'refused'

    async def test_nul_in_an_argument_is_refused(self) -> None:
        child = ChildPython(script='pass')

        outcome = await self.runner.run([*child.argv, 'a\x00b'], timeout=30)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'refused'

    @pytest.fixture
    def child_marker(self) -> str:
        return f'mightymodels-timed-out-child-{uuid.uuid4().hex}'

    async def test_run_past_the_timeout_is_timed_out_and_the_child_is_gone(
        self, child_marker: str
    ) -> None:
        child = ChildPython(script='import time; time.sleep(60)')

        outcome = await self.runner.run([*child.argv, child_marker], timeout=self.timeout)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'timed_out'
        assert not process_with_argument_runs(child_marker)

    async def test_output_that_is_not_text_is_undecodable(self) -> None:
        child = ChildPython(script='import sys; sys.stdout.buffer.write(b"\\xff\\xfe\\xfd")')

        outcome = await self.runner.run(child.argv, timeout=30)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'undecodable'
