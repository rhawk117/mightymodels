"""The runner harness and its fakes: a real repository, real sqlite and recorded progress."""

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.contract import (
    ApprovedCommand,
    ContractRunner,
    RunOptions,
    RunRequest,
    child_environment,
)
from mightymodels_core.git import GitCommand, ProcessGit
from mightymodels_core.primitives import RepositoryKey, Slug
from mightymodels_core.process import ChildSetting, CompletedRun, SubprocessRunner
from mightymodels_core.units_of_work import TaskWork

from tests.core.contract.contract_builders import SERVICE_MOMENT, create_ticket_section
from tests.core.git.git_builders import commit_file, run_git
from tests.core.primitives.clock import create_fake_clock

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    import anyio
    from mightymodels_core.contract import RunProgress
    from mightymodels_core.database import Database
    from mightymodels_core.process import ProcessRunner, RunOutcome

SLUG = Slug('runner-subject')
WAIT_SECONDS = 20


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
    setting: ChildSetting


@dataclass(slots=True, kw_only=True, frozen=True)
class WaitingRunner:
    released: anyio.Event
    launched: list[LaunchedRun] = field(default_factory=list)

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,  # noqa: ASYNC109  the ProcessRunner Protocol fixes this signature; the fake records the timeout, never enforces it
        setting: ChildSetting = ChildSetting(),  # noqa: B008  a frozen value, shared safely
    ) -> RunOutcome:
        self.launched.append(LaunchedRun(argv=tuple(argv), timeout=timeout, setting=setting))
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
