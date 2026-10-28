"""The contract run use case over the fakes: pick, run, receipt and record."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import ContractRunner, RunRequest, UnknownCommandError
from mightymodels_core.process import CompletedRun, FailedRun

from tests.core.contract.contract_builders import (
    FIRST_KEY,
    SECOND_KEY,
    SERVICE_MOMENT,
    SERVICE_SLUG,
    create_command,
)
from tests.core.contract.fakes import FakeProcessRunner
from tests.core.git.fakes import InMemoryGit
from tests.core.primitives.clock import create_fake_clock

if TYPE_CHECKING:
    from tests.core.contract.contract_builders import ServiceHarness

ROOT = Path('/repository')


@dataclass(slots=True, kw_only=True, frozen=True)
class RunHarness:
    service_harness: ServiceHarness
    processes: FakeProcessRunner
    git: InMemoryGit
    runner: ContractRunner

    @property
    def recorded(self) -> list[object]:
        return list(self.service_harness.ledger.receipts)


def create_git() -> InMemoryGit:
    git = InMemoryGit()
    git.history.commit('a.py')
    return git


def create_runner(
    service_harness: ServiceHarness, processes: FakeProcessRunner, git: InMemoryGit | None = None
) -> RunHarness:
    git = git or create_git()
    runner = ContractRunner(
        service=service_harness.service,
        processes=processes,
        git=git,
        clock=create_fake_clock(SERVICE_MOMENT),
        root=ROOT,
    )
    return RunHarness(service_harness=service_harness, processes=processes, git=git, runner=runner)


@pytest.fixture
def run_harness(stocked_service_harness: ServiceHarness) -> RunHarness:
    return create_runner(stocked_service_harness, FakeProcessRunner())


class TestSelection:
    async def test_all_approved_commands_run_when_none_are_asked(
        self, run_harness: RunHarness
    ) -> None:
        result = await run_harness.runner.run(
            RunRequest(slug=SERVICE_SLUG, asked=None, phase='task')
        )

        assert [receipt.key for receipt in result.receipts] == [FIRST_KEY, SECOND_KEY]
        assert len(run_harness.recorded) == 2

    async def test_only_the_asked_commands_run(self, run_harness: RunHarness) -> None:
        result = await run_harness.runner.run(
            RunRequest(slug=SERVICE_SLUG, asked=[SECOND_KEY], phase='task')
        )

        assert [receipt.key for receipt in result.receipts] == [SECOND_KEY]

    async def test_an_id_outside_the_contract_is_refused_before_anything_runs(
        self, run_harness: RunHarness
    ) -> None:
        request = RunRequest(slug=SERVICE_SLUG, asked=[FIRST_KEY, 'T9.AC-9'], phase='task')

        with pytest.raises(UnknownCommandError):
            await run_harness.runner.run(request)

        assert run_harness.processes.runs == []
        assert run_harness.recorded == []


class TestLaunch:
    async def test_the_stored_argv_runs_unchanged_with_the_command_timeout(
        self, service_harness: ServiceHarness
    ) -> None:
        argv = ('uv', 'run', 'pytest', '-q', 'a b; rm -rf /')
        command = create_command(FIRST_KEY, argv=argv)
        service_harness.service.approve(SERVICE_SLUG, [command], None)
        harness = create_runner(service_harness, FakeProcessRunner())

        await harness.runner.run(RunRequest(slug=SERVICE_SLUG, asked=None, phase='task'))

        (launched,) = harness.processes.runs
        assert launched.argv == argv
        assert not isinstance(launched.argv, str)
        assert launched.timeout == command.timeout
        assert launched.cwd == ROOT


class TestOutcome:
    async def test_a_timed_out_run_is_a_failing_receipt(
        self, stocked_service_harness: ServiceHarness
    ) -> None:
        timed_out = FailedRun(kind='timed_out', detail='exceeded 300s', stdout='half', stderr='')
        harness = create_runner(stocked_service_harness, FakeProcessRunner(reply=timed_out))

        result = await harness.runner.run(
            RunRequest(slug=SERVICE_SLUG, asked=[FIRST_KEY], phase='task')
        )

        (receipt,) = result.receipts
        assert receipt.outcome == 'timeout'
        assert receipt.exit is None
        assert receipt.stdout_tail == 'half'
        assert receipt.stderr_tail.endswith('exceeded 300s')
        assert not result.is_passing

    async def test_the_expected_exit_code_passes(self, run_harness: RunHarness) -> None:
        result = await run_harness.runner.run(
            RunRequest(slug=SERVICE_SLUG, asked=[FIRST_KEY], phase='review')
        )

        (receipt,) = result.receipts
        assert receipt.outcome == 'pass'
        assert receipt.exit == 0
        assert receipt.phase == 'review'
        assert receipt.head == run_harness.git.history.head()
        assert result.is_passing

    async def test_another_exit_code_fails(self, stocked_service_harness: ServiceHarness) -> None:
        refused = CompletedRun(exit=2, stdout='', stderr='boom')
        harness = create_runner(stocked_service_harness, FakeProcessRunner(reply=refused))

        result = await harness.runner.run(
            RunRequest(slug=SERVICE_SLUG, asked=[FIRST_KEY], phase='task')
        )

        (receipt,) = result.receipts
        assert receipt.outcome == 'fail'
        assert receipt.exit == 2
        assert receipt.stderr_tail == 'boom'
        assert not result.is_passing

    async def test_a_head_that_moved_during_the_run_cannot_pass(
        self, stocked_service_harness: ServiceHarness
    ) -> None:
        git = create_git()
        moving = FakeProcessRunner(moves_head=git.history)
        harness = create_runner(stocked_service_harness, moving, git)

        result = await harness.runner.run(
            RunRequest(slug=SERVICE_SLUG, asked=[FIRST_KEY], phase='task')
        )

        (receipt,) = result.receipts
        assert receipt.outcome == 'fail'
        assert 'HEAD changed' in receipt.stderr_tail
