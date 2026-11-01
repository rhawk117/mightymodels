"""The contract runner over a real repository, real processes and real sqlite."""

from typing import TYPE_CHECKING

import anyio
import pytest
from mightymodels_core.contract import (
    RetireRequest,
    TrackedChangesError,
    UnknownCommandError,
)

from tests.core.contract.runner_builders import (
    SLUG,
    WAIT_SECONDS,
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

LONG_OUTPUT = 'print("\\n".join(f"line {n}" for n in range(100)))'


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('repository')
    path.mkdir()
    return path


class TestSelection:
    unordered = (approved('I2', 'pass'), approved('I10', 'pass'), approved('I1', 'pass'))
    pair = (approved('I1', 'pass'), approved('I2', 'pass'))
    failing_first = (approved('I1', 'raise SystemExit(3)'), approved('I2', 'pass'))

    @pytest.fixture
    async def unordered_harness(self, root: Path, database: Database) -> RunnerHarness:
        return await create_harness(root, database, self.unordered)

    @pytest.fixture
    async def retired_harness(self, root: Path, database: Database) -> RunnerHarness:
        harness = await create_harness(root, database, self.pair)
        with harness.work.write() as unit:
            unit.contracts.retire(
                SLUG,
                RetireRequest(key='I1', by='planner', why='obsolete', approval_source='fallback'),
            )
        return harness

    @pytest.fixture
    async def single_harness(self, root: Path, database: Database) -> RunnerHarness:
        return await create_harness(root, database, [approved('I1', 'pass')])

    @pytest.fixture
    async def failing_harness(self, root: Path, database: Database) -> RunnerHarness:
        return await create_harness(root, database, self.failing_first)

    @pytest.fixture
    async def exclusive_harness(self, root: Path, database: Database) -> RunnerHarness:
        marker = root.parent.joinpath('marker')
        source = (
            f'import pathlib, time; m = pathlib.Path({str(marker)!r}); '
            'assert not m.exists(); m.write_text("x"); time.sleep(0.2); m.unlink()'
        )
        return await create_harness(
            root, database, [approved('I1', source), approved('I2', source)]
        )

    async def test_no_ids_runs_every_live_command_in_approved_order(
        self, unordered_harness: RunnerHarness
    ) -> None:
        result = await unordered_harness.runner.run(request())

        assert [receipt.key for receipt in result.receipts] == ['I2', 'I10', 'I1']
        assert result.is_passing

    async def test_a_retired_command_is_skipped(self, retired_harness: RunnerHarness) -> None:
        result = await retired_harness.runner.run(request())

        assert [receipt.key for receipt in result.receipts] == ['I2']

    async def test_an_unknown_id_is_refused_before_anything_runs(
        self, single_harness: RunnerHarness
    ) -> None:
        with pytest.raises(UnknownCommandError):
            await single_harness.runner.run(request(['I1', 'I9']))

        assert single_harness.receipts() == {}

    async def test_the_run_continues_after_a_failure(self, failing_harness: RunnerHarness) -> None:
        result = await failing_harness.runner.run(request())

        assert [receipt.outcome for receipt in result.receipts] == ['fail', 'pass']
        assert not result.is_passing
        assert failing_harness.receipts() == {'I1': 'fail', 'I2': 'pass'}

    async def test_commands_run_one_at_a_time(self, exclusive_harness: RunnerHarness) -> None:
        result = await exclusive_harness.runner.run(request())

        assert result.is_passing


class TestGitState:
    head_moving = (
        'import subprocess; subprocess.run(["git", "-c", "user.name=T", "-c", '
        '"user.email=t@example.com", "commit", "--allow-empty", "-m", "moved"], check=True)'
    )
    edit = 'import pathlib; pathlib.Path("tracked.txt").write_text("edited")'

    @pytest.fixture
    async def single_harness(self, root: Path, database: Database) -> RunnerHarness:
        return await create_harness(root, database, [approved('I1', 'pass')])

    @pytest.fixture
    async def dirty_harness(self, single_harness: RunnerHarness) -> RunnerHarness:
        await anyio.Path(single_harness.root, 'tracked.txt').write_text('changed')
        return single_harness

    @pytest.fixture
    async def untracked_harness(self, single_harness: RunnerHarness) -> RunnerHarness:
        await anyio.Path(single_harness.root, 'scratch.txt').write_text('new')
        return single_harness

    @pytest.fixture
    async def head_moving_harness(self, root: Path, database: Database) -> RunnerHarness:
        return await create_harness(root, database, [approved('I1', self.head_moving)])

    @pytest.fixture
    async def editing_harness(self, root: Path, database: Database) -> RunnerHarness:
        commands = [approved('I1', self.edit), approved('I2', 'pass')]
        return await create_harness(root, database, commands)

    async def test_tracked_changes_refuse_the_run(self, dirty_harness: RunnerHarness) -> None:
        with pytest.raises(TrackedChangesError) as refused:
            await dirty_harness.runner.run(request())

        assert refused.value.paths == ('tracked.txt',)
        assert dirty_harness.receipts() == {}

    async def test_untracked_files_do_not_refuse_the_run(
        self, untracked_harness: RunnerHarness
    ) -> None:
        result = await untracked_harness.runner.run(request())

        assert result.is_passing

    async def test_head_moving_during_a_run_records_fail(
        self, head_moving_harness: RunnerHarness
    ) -> None:
        result = await head_moving_harness.runner.run(request())

        (receipt,) = result.receipts
        assert receipt.outcome == 'fail'
        assert receipt.exit == 0
        assert 'HEAD changed during verification' in receipt.stderr_tail

    async def test_a_command_that_edits_a_tracked_file_and_later_ones_do_not_pass(
        self, editing_harness: RunnerHarness
    ) -> None:
        result = await editing_harness.runner.run(request())

        first, second = result.receipts
        assert [first.outcome, second.outcome] == ['fail', 'fail']
        assert first.exit == 0
        assert 'Tracked files changed during verification' in first.stderr_tail
        assert not result.is_passing


class TestReceipt:
    commands = (
        approved('I1', LONG_OUTPUT),
        approved('I2', 'print("a" * 9000)'),
        approved('I3', 'print("token=ghp_abcdefghijklmnopqrstuvwxyz0123456789")'),
    )

    @pytest.fixture
    async def harness(self, root: Path, database: Database) -> RunnerHarness:
        return await create_harness(root, database, self.commands)

    async def test_receipts_keep_forty_lines_and_four_thousand_characters_redacted(
        self, harness: RunnerHarness
    ) -> None:
        result = await harness.runner.run(request())

        lines, characters, redacted = result.receipts
        assert lines.stdout_tail.splitlines()[0] == 'line 60'
        assert len(lines.stdout_tail.splitlines()) == 40
        assert len(characters.stdout_tail) == 4000
        assert 'ghp_abcdefghijklmnopqrstuvwxyz0123456789' not in redacted.stdout_tail


class TestInterruption:
    commands = (approved('I1', 'pass'), approved('I2', 'import time; time.sleep(60)'))

    @pytest.fixture
    async def harness(self, root: Path, database: Database) -> RunnerHarness:
        return await create_harness(root, database, self.commands)

    @pytest.fixture
    def second_started(self, harness: RunnerHarness) -> anyio.Event:
        started = anyio.Event()
        harness.reporter.on_report = started
        harness.reporter.trigger = ('I2', 'started')
        return started

    async def test_a_cancelled_run_keeps_the_receipt_of_the_finished_command(
        self, harness: RunnerHarness, second_started: anyio.Event
    ) -> None:
        with anyio.fail_after(WAIT_SECONDS):
            async with anyio.create_task_group() as group:

                async def cancel_when_second_starts() -> None:
                    await second_started.wait()
                    group.cancel_scope.cancel()

                group.start_soon(cancel_when_second_starts)
                await harness.runner.run(request())

        assert harness.receipts() == {'I1': 'pass'}
