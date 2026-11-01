import os
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
import pytest
from mightymodels_core.process import (
    ChildSetting,
    CompletedRun,
    FailedRun,
    SubprocessRunner,
    launch,
    settle,
)

if TYPE_CHECKING:
    from pathlib import Path

WAIT_SECONDS = 10
POLL_SECONDS = 0.05
SETTLE_SECONDS = 0.5


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

    probe_script = 'import os; print(os.environ.get("MM_PROBE"))'

    @pytest.fixture
    def marker(self, tmp_path: Path) -> Path:
        return tmp_path.joinpath('pids')

    @pytest.fixture
    def inherited_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('MM_PROBE', 'inherited')

    def spawning_argv(self, marker: Path) -> list[str]:
        return [sys.executable, '-c', self.spawning_script, str(marker)]

    async def test_timeout_ends_child_and_grandchild(self, marker: Path) -> None:
        launched = await launch(self.spawning_argv(marker), ChildSetting())
        assert not isinstance(launched, FailedRun)
        pair = await wait_for_pair(marker)

        outcome = await settle(launched, timeout=SETTLE_SECONDS)

        assert isinstance(outcome, FailedRun)
        assert outcome.kind == 'timed_out'
        assert await wait_until_gone(pair.child)
        assert await wait_until_gone(pair.grandchild)

    async def test_cancellation_ends_both_and_is_returned_to_the_caller(self, marker: Path) -> None:
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
        outcome = await self.runner.run(
            [sys.executable, '-c', self.probe_script],
            timeout=30,
            setting=ChildSetting(env={'MM_PROBE': 'given'}),
        )

        assert outcome == CompletedRun(exit=0, stdout='given\n', stderr='')

    @pytest.mark.usefixtures('inherited_probe')
    async def test_omitted_env_inherits_the_parent_environment(self) -> None:
        outcome = await self.runner.run([sys.executable, '-c', self.probe_script], timeout=30)

        assert outcome == CompletedRun(exit=0, stdout='inherited\n', stderr='')
