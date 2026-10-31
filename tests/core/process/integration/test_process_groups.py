import os
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
from mightymodels_core.process import CompletedRun, FailedRun, SubprocessRunner

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

WAIT_SECONDS = 10
POLL_SECONDS = 0.05


@dataclass(slots=True, kw_only=True, frozen=True)
class ProcessPair:
    child: int
    grandchild: int


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False

    return True


def block_until_gone(pid: int) -> bool:
    deadline = time.monotonic() + WAIT_SECONDS
    while is_alive(pid) and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)

    return not is_alive(pid)


def block_for_pair(marker: Path) -> ProcessPair:
    deadline = time.monotonic() + WAIT_SECONDS
    while not marker.exists() or len(marker.read_text().split()) != 2:
        if time.monotonic() > deadline:
            raise TimeoutError(str(marker))

        time.sleep(POLL_SECONDS)

    child, grandchild = marker.read_text().split()
    return ProcessPair(child=int(child), grandchild=int(grandchild))


async def wait_until_gone(pid: int) -> bool:
    return await anyio.to_thread.run_sync(block_until_gone, pid)


async def wait_for_pair(marker: Path) -> ProcessPair:
    return await anyio.to_thread.run_sync(block_for_pair, marker)


class TestSubprocessRunnerGroups:
    runner = SubprocessRunner()
    spawning_script = (
        'import os, subprocess, sys, time\n'
        'grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
        'open(sys.argv[1], "w").write(f"{os.getpid()} {grandchild.pid}")\n'
        'time.sleep(60)\n'
    )

    def spawning_argv(self, marker: Path) -> list[str]:
        return [sys.executable, '-c', self.spawning_script, str(marker)]

    async def test_timeout_ends_child_and_grandchild(self, tmp_path: Path) -> None:
        marker = tmp_path.joinpath('pids')

        outcome = await self.runner.run(self.spawning_argv(marker), timeout=2)

        pair = await wait_for_pair(marker)
        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'timed_out'
        assert await wait_until_gone(pair.child)
        assert await wait_until_gone(pair.grandchild)

    async def test_cancellation_ends_both_and_is_returned_to_the_caller(
        self, tmp_path: Path
    ) -> None:
        marker = tmp_path.joinpath('pids')
        returned = False

        with anyio.CancelScope() as scope:
            async with anyio.create_task_group() as group:

                async def cancel_once_started() -> None:
                    await wait_for_pair(marker)
                    scope.cancel()

                group.start_soon(cancel_once_started)
                await self.runner.run(self.spawning_argv(marker), timeout=60)
                returned = True

        pair = await wait_for_pair(marker)
        assert scope.cancelled_caught
        assert not returned
        assert await wait_until_gone(pair.child)
        assert await wait_until_gone(pair.grandchild)

    async def test_given_env_reaches_the_child(self) -> None:
        script = 'import os; print(os.environ.get("MM_PROBE"))'

        outcome = await self.runner.run(
            [sys.executable, '-c', script], timeout=30, env={'MM_PROBE': 'given'}
        )

        assert outcome == CompletedRun(exit=0, stdout='given\n', stderr='')

    async def test_omitted_env_inherits_the_parent_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('MM_PROBE', 'inherited')
        script = 'import os; print(os.environ.get("MM_PROBE"))'

        outcome = await self.runner.run([sys.executable, '-c', script], timeout=30)

        assert outcome == CompletedRun(exit=0, stdout='inherited\n', stderr='')
