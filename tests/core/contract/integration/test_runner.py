"""The contract runner over a real repository, real processes and real sqlite."""

import sys
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import anyio
import pytest
from mightymodels_core.contract import (
    ApprovedCommand,
    ContractRunner,
    RetireRequest,
    RunOptions,
    RunReporter,
    RunRequest,
    TrackedChangesError,
    UnknownCommandError,
    child_environment,
)
from mightymodels_core.git import GitCommand, ProcessGit
from mightymodels_core.primitives import RepositoryKey, Slug
from mightymodels_core.process import CompletedRun, SubprocessRunner
from mightymodels_core.units_of_work import TaskWork

from tests.core.contract.contract_builders import SERVICE_MOMENT, create_ticket_section
from tests.core.git.git_builders import commit_file, run_git
from tests.core.primitives.clock import create_fake_clock

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from mightymodels_core.contract import RunProgress
    from mightymodels_core.database import Database
    from mightymodels_core.process import ProcessRunner, RunOutcome

SLUG = Slug('runner-subject')
WAIT_SECONDS = 20
LONG_OUTPUT = 'print("\\n".join(f"line {n}" for n in range(100)))'
HEARTBEAT_SECONDS = 0.01


def program(source: str) -> tuple[str, ...]:
    return (sys.executable, '-c', source)


def approved(key: str, source: str, *, expect_exit: int = 0) -> ApprovedCommand:
    return ApprovedCommand(
        key=key, argv=program(source), expect_exit=expect_exit, timeout=60, approved_by='planner'
    )


@dataclass(slots=True, kw_only=True)
class RecordingReporter:
    seen: list[RunProgress] = field(default_factory=list)
    on_report: anyio.Event | None = None
    trigger: tuple[str, str] | None = None

    async def report(self, progress: RunProgress) -> None:
        self.seen.append(progress)
        if self.on_report is not None and (progress.key, progress.state) == self.trigger:
            self.on_report.set()


@dataclass(slots=True, kw_only=True, frozen=True)
class RaisingReporter:
    async def report(self, progress: RunProgress) -> None:
        raise RuntimeError(progress.state)


@dataclass(slots=True, kw_only=True, frozen=True)
class LaunchedRun:
    argv: tuple[str, ...]
    timeout: float
    cwd: Path | None
    env: Mapping[str, str] | None


@dataclass(slots=True, kw_only=True, frozen=True)
class WaitingRunner:
    released: anyio.Event
    launched: list[LaunchedRun] = field(default_factory=list)

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,  # noqa: ASYNC109  the ProcessRunner Protocol fixes this signature; the fake records the timeout, never enforces it
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> RunOutcome:
        self.launched.append(LaunchedRun(argv=tuple(argv), timeout=timeout, cwd=cwd, env=env))
        await self.released.wait()
        return CompletedRun(exit=0, stdout='', stderr='')


@dataclass(slots=True, kw_only=True, frozen=True)
class RunnerHarness:
    runner: ContractRunner
    work: TaskWork
    reporter: RecordingReporter
    root: Path

    def receipts(self) -> dict[str, str]:
        with self.work.read() as unit:
            return {
                key: receipt.outcome
                for key, receipt in unit.task_reads.contracts.latest_receipts(
                    unit.tasks.tickets.staged_ticket(SLUG).id
                ).items()
            }


async def create_harness(
    root: Path,
    database: Database,
    commands: Sequence[ApprovedCommand],
    *,
    processes: ProcessRunner | None = None,
    options: RunOptions | None = None,
) -> RunnerHarness:
    await run_git(root, 'init', '--initial-branch', 'main')
    await commit_file(root, 'tracked.txt')
    clock = create_fake_clock(SERVICE_MOMENT)
    work = TaskWork(database=database, repository_key=RepositoryKey('owner/repo'), clock=clock)
    with work.write() as unit:
        unit.tasks.tickets.stage(SLUG, create_ticket_section(SLUG), ())
        unit.contracts.approve(SLUG, commands, None)
    reporter = RecordingReporter()
    git = ProcessGit(command=GitCommand(root=root, executable='git', processes=SubprocessRunner()))
    runner = ContractRunner(
        work=work,
        processes=processes or SubprocessRunner(),
        git=git,
        clock=clock,
        root=root,
        environment=child_environment({'PATH': '/usr/bin:/bin'}),
        reporter=reporter,
        options=options or RunOptions(),
    )
    return RunnerHarness(runner=runner, work=work, reporter=reporter, root=root)


def request(asked: Sequence[str] | None = None) -> RunRequest:
    return RunRequest(slug=SLUG, asked=asked, phase='task')


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('repository')
    path.mkdir()
    return path


class TestSelection:
    async def test_no_ids_runs_every_live_command_in_approved_order(
        self, root: Path, database: Database
    ) -> None:
        commands = [approved('I2', 'pass'), approved('I10', 'pass'), approved('I1', 'pass')]
        harness = await create_harness(root, database, commands)

        result = await harness.runner.run(request())

        assert [receipt.key for receipt in result.receipts] == ['I2', 'I10', 'I1']
        assert result.is_passing

    async def test_a_retired_command_is_skipped(self, root: Path, database: Database) -> None:
        harness = await create_harness(
            root, database, [approved('I1', 'pass'), approved('I2', 'pass')]
        )
        with harness.work.write() as unit:
            unit.contracts.retire(
                SLUG,
                RetireRequest(key='I1', by='planner', why='obsolete', approval_source='fallback'),
            )

        result = await harness.runner.run(request())

        assert [receipt.key for receipt in result.receipts] == ['I2']

    async def test_an_unknown_id_is_refused_before_anything_runs(
        self, root: Path, database: Database
    ) -> None:
        harness = await create_harness(root, database, [approved('I1', 'pass')])

        with pytest.raises(UnknownCommandError):
            await harness.runner.run(request(['I1', 'I9']))

        assert harness.receipts() == {}

    async def test_the_run_continues_after_a_failure(self, root: Path, database: Database) -> None:
        commands = [approved('I1', 'raise SystemExit(3)'), approved('I2', 'pass')]
        harness = await create_harness(root, database, commands)

        result = await harness.runner.run(request())

        assert [receipt.outcome for receipt in result.receipts] == ['fail', 'pass']
        assert not result.is_passing
        assert harness.receipts() == {'I1': 'fail', 'I2': 'pass'}

    async def test_commands_run_one_at_a_time(self, root: Path, database: Database) -> None:
        marker = root.parent.joinpath('marker')
        source = (
            f'import pathlib, time; m = pathlib.Path({str(marker)!r}); '
            'assert not m.exists(); m.write_text("x"); time.sleep(0.2); m.unlink()'
        )
        commands = [approved('I1', source), approved('I2', source)]
        harness = await create_harness(root, database, commands)

        result = await harness.runner.run(request())

        assert result.is_passing


class TestGitState:
    async def test_tracked_changes_refuse_the_run(self, root: Path, database: Database) -> None:
        harness = await create_harness(root, database, [approved('I1', 'pass')])
        await anyio.Path(root, 'tracked.txt').write_text('changed')

        with pytest.raises(TrackedChangesError) as refused:
            await harness.runner.run(request())

        assert refused.value.paths == ('tracked.txt',)
        assert harness.receipts() == {}

    async def test_untracked_files_do_not_refuse_the_run(
        self, root: Path, database: Database
    ) -> None:
        harness = await create_harness(root, database, [approved('I1', 'pass')])
        await anyio.Path(root, 'scratch.txt').write_text('new')

        result = await harness.runner.run(request())

        assert result.is_passing

    async def test_head_moving_during_a_run_records_fail(
        self, root: Path, database: Database
    ) -> None:
        source = (
            'import subprocess; subprocess.run(["git", "-c", "user.name=T", "-c", '
            '"user.email=t@example.com", "commit", "--allow-empty", "-m", "moved"], check=True)'
        )
        harness = await create_harness(root, database, [approved('I1', source)])

        result = await harness.runner.run(request())

        (receipt,) = result.receipts
        assert receipt.outcome == 'fail'
        assert receipt.exit == 0
        assert 'HEAD changed during verification' in receipt.stderr_tail

    async def test_a_command_that_edits_a_tracked_file_and_later_ones_do_not_pass(
        self, root: Path, database: Database
    ) -> None:
        edit = 'import pathlib; pathlib.Path("tracked.txt").write_text("edited")'
        harness = await create_harness(
            root, database, [approved('I1', edit), approved('I2', 'pass')]
        )

        result = await harness.runner.run(request())

        first, second = result.receipts
        assert [first.outcome, second.outcome] == ['fail', 'fail']
        assert first.exit == 0
        assert 'Tracked files changed during verification' in first.stderr_tail
        assert not result.is_passing


class TestReceipt:
    async def test_receipts_keep_forty_lines_and_four_thousand_characters_redacted(
        self, root: Path, database: Database
    ) -> None:
        long_lines = approved('I1', LONG_OUTPUT)
        wide = approved('I2', 'print("a" * 9000)')
        secret = approved('I3', 'print("token=ghp_abcdefghijklmnopqrstuvwxyz0123456789")')
        harness = await create_harness(root, database, [long_lines, wide, secret])

        result = await harness.runner.run(request())

        lines, characters, redacted = result.receipts
        assert lines.stdout_tail.splitlines()[0] == 'line 60'
        assert len(lines.stdout_tail.splitlines()) == 40
        assert len(characters.stdout_tail) == 4000
        assert 'ghp_abcdefghijklmnopqrstuvwxyz0123456789' not in redacted.stdout_tail


class TestProgress:
    async def test_each_command_reports_a_start_and_an_end(
        self, root: Path, database: Database
    ) -> None:
        harness = await create_harness(
            root, database, [approved('I1', 'pass'), approved('I2', 'raise SystemExit(1)')]
        )

        await harness.runner.run(request())

        steps = [
            (seen.key, seen.position, seen.total, seen.state, seen.outcome)
            for seen in harness.reporter.seen
            if seen.state != 'running'
        ]
        assert steps == [
            ('I1', 1, 2, 'started', None),
            ('I1', 1, 2, 'finished', 'pass'),
            ('I2', 2, 2, 'started', None),
            ('I2', 2, 2, 'finished', 'fail'),
        ]

    async def test_a_heartbeat_is_reported_while_a_command_runs(
        self, root: Path, database: Database
    ) -> None:
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

        with anyio.fail_after(WAIT_SECONDS):
            await harness.runner.run(request())

        states = [seen.state for seen in harness.reporter.seen]
        assert states[0] == 'started'
        assert 'running' in states
        assert states[-1] == 'finished'
        (launched,) = waiting.launched
        assert launched.env == {'PATH': '/usr/bin:/bin'}
        assert launched.cwd == root

    async def test_a_raising_reporter_costs_no_command_and_no_receipt(
        self, root: Path, database: Database
    ) -> None:
        harness = await create_harness(
            root,
            database,
            [approved('I1', 'pass'), approved('I2', 'pass')],
            options=RunOptions(heartbeat_seconds=HEARTBEAT_SECONDS),
        )
        runner = replace(harness.runner, reporter=RaisingReporter())

        result = await runner.run(request())

        assert [receipt.outcome for receipt in result.receipts] == ['pass', 'pass']
        assert harness.receipts() == {'I1': 'pass', 'I2': 'pass'}

    async def test_the_reporter_is_a_protocol(self) -> None:
        assert isinstance(RecordingReporter(), RunReporter)


class TestInterruption:
    async def test_a_cancelled_run_keeps_the_receipt_of_the_finished_command(
        self, root: Path, database: Database
    ) -> None:
        commands = [approved('I1', 'pass'), approved('I2', 'import time; time.sleep(60)')]
        harness = await create_harness(root, database, commands)
        second_started = anyio.Event()
        harness.reporter.on_report = second_started
        harness.reporter.trigger = ('I2', 'started')

        with anyio.fail_after(WAIT_SECONDS):
            async with anyio.create_task_group() as group:

                async def cancel_when_second_starts() -> None:
                    await second_started.wait()
                    group.cancel_scope.cancel()

                group.start_soon(cancel_when_second_starts)
                await harness.runner.run(request())

        assert harness.receipts() == {'I1': 'pass'}
