from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import commit_file
from tests.hooks.completion_gate.completion_gate_builders import (
    ARCHITECT,
    ENGINEER,
    INTERN,
    OUTSIDE,
    OWNED,
    ResidualScene,
    SeededTask,
)

if TYPE_CHECKING:
    from mightymodels_core.vocabulary.tasks import Worker

    from tests.hooks.completion_gate.completion_gate_builders import CompletionHarness

type Staging = Callable[[ResidualScene], Awaitable[None]]

NO_RECEIPT = 'R1.AC-1 has no receipt at the current HEAD'


async def nothing_committed(scene: ResidualScene) -> None:
    await scene.start()


async def fixed_without_a_receipt(scene: ResidualScene) -> None:
    await scene.start()
    await scene.harness.approve()
    await scene.fix(OWNED)


async def proven_before_the_fix(scene: ResidualScene) -> None:
    await scene.start()
    await scene.harness.approve()
    await scene.harness.record(scene.base, 'pass')
    await scene.fix(OWNED)


async def fixed_and_failing(scene: ResidualScene) -> None:
    await scene.start()
    await scene.harness.approve()
    await scene.harness.record(await scene.fix(OWNED), 'fail')


async def fixed_outside_the_owned_set(scene: ResidualScene) -> None:
    await scene.start()
    await scene.harness.approve()
    await scene.fix(OWNED)
    await scene.harness.record(await scene.fix(OUTSIDE), 'pass')


async def fixed_and_proven(scene: ResidualScene) -> None:
    await scene.start()
    await scene.harness.approve()
    await scene.harness.record(await scene.fix(OWNED), 'pass')


async def fixed_with_no_contract_command(scene: ResidualScene) -> None:
    await scene.start()
    await scene.fix(OWNED)


async def check_fix_with_nothing_committed(scene: ResidualScene) -> None:
    await scene.start('C1')


def held_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('staging', 'lack'),
        [
            pytest.param(nothing_committed, 'no commit follows its base', id='no-commit'),
            pytest.param(fixed_without_a_receipt, NO_RECEIPT, id='no-receipt'),
            pytest.param(proven_before_the_fix, NO_RECEIPT, id='receipt-at-an-older-commit'),
            pytest.param(fixed_and_failing, 'R1.AC-1 fail at HEAD', id='failed-receipt'),
            pytest.param(
                fixed_outside_the_owned_set,
                f'changed outside the owned set: {OUTSIDE}',
                id='outside-the-owned-set',
            ),
        ],
    )


def let_through_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'staging',
        [
            pytest.param(fixed_and_proven, id='committed-proven-and-inside-the-owned-set'),
            pytest.param(fixed_with_no_contract_command, id='no-contract-command'),
            pytest.param(check_fix_with_nothing_committed, id='check-fix'),
        ],
    )


def implementer_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('agent_type', 'worker'),
        [
            pytest.param(ENGINEER, 'engineer', id='engineer'),
            pytest.param(ARCHITECT, 'architect', id='architect'),
            pytest.param(INTERN, 'intern', id='intern'),
        ],
    )


class TestCompletionGateOnAResidual:
    @pytest.fixture
    async def scene(self, harness: CompletionHarness) -> ResidualScene:
        base = await commit_file(harness.checkout, 'seed.txt')
        return ResidualScene(harness=harness, base=base)

    @held_cases()
    async def test_it_holds_the_stop_naming_what_the_residual_lacks_and_no_brief(
        self, staging: Staging, lack: str, scene: ResidualScene
    ) -> None:
        await staging(scene)
        reply = await scene.harness.stop()
        assert reply.decision == 'block'
        assert f'R1 is in progress and {lack}' in reply.reason
        assert 'mightymodels verify run --slug port-it --id' in reply.reason
        assert 'brief' not in reply.reason

    @let_through_cases()
    async def test_it_lets_the_stop_through_with_no_brief_written(
        self, staging: Staging, scene: ResidualScene
    ) -> None:
        await staging(scene)
        assert (await scene.harness.stop()).output is None
        assert not scene.harness.checkout.joinpath('.mightymodels/port-it/briefs').exists()

    @implementer_cases()
    async def test_it_holds_whichever_implementer_started_the_residual(
        self, agent_type: str, worker: Worker, scene: ResidualScene
    ) -> None:
        await scene.start(worker=worker)
        reply = await scene.harness.stop(agent_type)
        assert 'R1 is in progress and no commit follows its base' in reply.reason

    async def test_an_implementer_that_did_not_start_it_is_let_through(
        self, scene: ResidualScene
    ) -> None:
        await nothing_committed(scene)
        assert (await scene.harness.stop(ARCHITECT)).output is None

    async def test_a_second_stop_after_the_block_is_let_through(self, scene: ResidualScene) -> None:
        await nothing_committed(scene)
        assert (await scene.harness.stop(active=True)).output is None

    async def test_beside_a_plan_task_it_names_both_and_what_finishes_each(
        self, scene: ResidualScene
    ) -> None:
        await scene.harness.seed((SeededTask(key='R1'), SeededTask(key='T1')), base=scene.base)
        reply = await scene.harness.stop()
        assert 'T1 is in progress and its brief' in reply.reason
        assert 'R1 is in progress and no commit follows its base' in reply.reason
        assert 'Append the `## DONE` half' in reply.reason
        assert 'mightymodels verify run --slug port-it --id' in reply.reason
