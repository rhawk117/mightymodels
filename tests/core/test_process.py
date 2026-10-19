import os
import sys
from dataclasses import dataclass
from pathlib import Path

import anyio
import pytest
from mightymodels_core.process import CompletedRun, FailedRun, SubprocessRunner

pytestmark = pytest.mark.integration


@dataclass(slots=True, kw_only=True, frozen=True)
class ChildPython:
    script: str

    @property
    def argv(self) -> list[str]:
        return [sys.executable, '-c', self.script]


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def is_same_directory(printed: str, expected: Path) -> bool:
    return Path(printed.strip()).resolve() == expected.resolve()


HEARTBEAT_SCRIPT = """
import time
with open({path!r}, 'ab', buffering=0) as heartbeat:
    for _ in range({ticks}):
        heartbeat.write(b'.')
        time.sleep(0.05)
"""


def heartbeat_ticks(heartbeat: Path) -> int:
    return heartbeat.stat().st_size if heartbeat.exists() else 0


class TestSubprocessRunner:
    runner = SubprocessRunner()
    timeout = 1
    child_ticks = 40
    child_lifetime = 2
    margin = 1

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
    def heartbeat(self, tmp_path: Path) -> Path:
        return tmp_path.joinpath('heartbeat')

    async def test_run_past_the_timeout_is_timed_out_and_the_child_is_gone(
        self, heartbeat: Path
    ) -> None:
        child = ChildPython(
            script=HEARTBEAT_SCRIPT.format(path=str(heartbeat), ticks=self.child_ticks)
        )

        outcome = await self.runner.run(child.argv, timeout=self.timeout)
        ticks_at_return = heartbeat_ticks(heartbeat)
        await anyio.sleep(self.child_lifetime + self.margin)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'timed_out'
        assert heartbeat_ticks(heartbeat) == ticks_at_return

    async def test_output_that_is_not_text_is_undecodable(self) -> None:
        child = ChildPython(script='import sys; sys.stdout.buffer.write(b"\\xff\\xfe\\xfd")')

        outcome = await self.runner.run(child.argv, timeout=30)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'undecodable'
