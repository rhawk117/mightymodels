"""The contract runner's progress: start and end reports, the heartbeat and a raising reporter."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import anyio
import pytest
from mightymodels_core.contract import RunOptions, RunReporter

from tests.core.contract.runner_builders import (
    WAIT_SECONDS,
    RaisingReporter,
    RecordingReporter,
    WaitingRunner,
    approved,
    create_harness,
    request,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.database import Database

    from tests.core.contract.runner_builders import (
        RunnerHarness,
    )

HEARTBEAT_SECONDS = 0.01


@dataclass(slots=True, kw_only=True, frozen=True)
class HeartbeatHarness:
    runner: RunnerHarness
    waiting: WaitingRunner


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('repository')
    path.mkdir()
    return path


class TestProgress:
    @pytest.fixture
    async def passing_and_failing(self, root: Path, database: Database) -> RunnerHarness:
        commands = [approved('I1', 'pass'), approved('I2', 'raise SystemExit(1)')]
        return await create_harness(root, database, commands)

    @pytest.fixture
    async def heartbeat(self, root: Path, database: Database) -> HeartbeatHarness:
        released = anyio.Event()
        waiting = WaitingRunner(released=released)
        harness = await create_harness(
            root,
            database,
            [approved('I1', 'pass')],
            processes=waiting,
            options=RunOptions(heartbeat_seconds=HEARTBEAT_SECONDS),
        )
        harness.reporter.on_report = released
        harness.reporter.trigger = ('I1', 'running')
        return HeartbeatHarness(runner=harness, waiting=waiting)

    @pytest.fixture
    async def raising(self, root: Path, database: Database) -> RunnerHarness:
        harness = await create_harness(
            root,
            database,
            [approved('I1', 'pass'), approved('I2', 'pass')],
            options=RunOptions(heartbeat_seconds=HEARTBEAT_SECONDS),
        )
        return replace(harness, runner=replace(harness.runner, reporter=RaisingReporter()))

    async def test_each_command_reports_a_start_and_an_end(
        self, passing_and_failing: RunnerHarness
    ) -> None:
        await passing_and_failing.runner.run(request())

        steps = [
            (seen.key, seen.position, seen.total, seen.state, seen.outcome)
            for seen in passing_and_failing.reporter.seen
            if seen.state != 'running'
        ]
        assert steps == [
            ('I1', 1, 2, 'started', None),
            ('I1', 1, 2, 'finished', 'pass'),
            ('I2', 2, 2, 'started', None),
            ('I2', 2, 2, 'finished', 'fail'),
        ]

    async def test_a_heartbeat_is_reported_while_a_command_runs(
        self, heartbeat: HeartbeatHarness
    ) -> None:
        with anyio.fail_after(WAIT_SECONDS):
            await heartbeat.runner.runner.run(request())

        states = [seen.state for seen in heartbeat.runner.reporter.seen]
        assert states[0] == 'started'
        assert 'running' in states
        assert states[-1] == 'finished'
        (launched,) = heartbeat.waiting.launched
        assert launched.setting.env == {'PATH': '/usr/bin:/bin'}
        assert launched.setting.cwd == heartbeat.runner.root

    async def test_a_raising_reporter_costs_no_command_and_no_receipt(
        self, raising: RunnerHarness
    ) -> None:
        result = await raising.runner.run(request())

        assert [receipt.outcome for receipt in result.receipts] == ['pass', 'pass']
        assert raising.receipts() == {'I1': 'pass', 'I2': 'pass'}

    async def test_the_reporter_is_a_protocol(self) -> None:
        assert isinstance(RecordingReporter(), RunReporter)
