import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from mightymodels_core.process import CompletedRun, FailedRun, SubprocessRunner


@dataclass(slots=True, kw_only=True, frozen=True)
class ChildPython:
    script: str

    @property
    def argv(self) -> list[str]:
        return [sys.executable, '-c', self.script]


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

    async def test_run_past_the_timeout_is_timed_out_and_the_child_is_gone(self) -> None:
        child = ChildPython(
            script='import os, signal; print(os.getpid(), flush=True); signal.pause()'
        )

        outcome = await self.runner.run(child.argv, timeout=self.timeout)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'timed_out'
        with pytest.raises(ProcessLookupError):
            os.kill(int(outcome.stdout), 0)

    async def test_output_that_is_not_text_is_undecodable(self) -> None:
        child = ChildPython(script='import sys; sys.stdout.buffer.write(b"\\xff\\xfe\\xfd")')

        outcome = await self.runner.run(child.argv, timeout=30)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'undecodable'
