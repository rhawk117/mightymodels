from typing import TYPE_CHECKING

import pytest

from tests.hooks.completion_gate.completion_gate_builders import (
    ARCHITECT,
    DONE_WITH_A_COMMIT,
    DONE_WITHOUT_A_COMMIT,
    ENGINEER,
    INTERN,
    SeededTask,
)

if TYPE_CHECKING:
    from tests.hooks.completion_gate.completion_gate_builders import CompletionHarness

ENGINEER_T1 = SeededTask(key='T1')
INTERN_T1 = SeededTask(key='T1', worker='intern')
OTHER_AGENTS = ('mightymodels:triage:code-scout', 'general-purpose', 'engineer', None)


def other_agent_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'agent_type', [pytest.param(agent, id=str(agent)) for agent in OTHER_AGENTS]
    )


class TestCompletionGateOnTheEngineer:
    @pytest.fixture
    async def engineer_on_t1(self, harness: CompletionHarness) -> None:
        await harness.seed((ENGINEER_T1,))

    @pytest.mark.usefixtures('engineer_on_t1')
    async def test_without_a_brief_it_blocks_naming_the_task_and_the_missing_brief(
        self, harness: CompletionHarness
    ) -> None:
        reply = await harness.stop()
        assert reply.decision == 'block'
        assert 'T1' in reply.reason
        assert 'task-01.md is missing' in reply.reason

    @pytest.mark.usefixtures('engineer_on_t1')
    async def test_with_a_done_half_naming_no_commit_it_blocks(
        self, harness: CompletionHarness
    ) -> None:
        harness.write_brief(1, DONE_WITHOUT_A_COMMIT)
        reply = await harness.stop()
        assert (reply.decision, 'has no DONE half naming a commit' in reply.reason) == (
            'block',
            True,
        )

    @pytest.mark.usefixtures('engineer_on_t1')
    async def test_with_a_done_half_naming_a_commit_it_lets_the_stop_through(
        self, harness: CompletionHarness
    ) -> None:
        harness.write_brief(1, DONE_WITH_A_COMMIT)
        assert (await harness.stop()).output is None

    @pytest.mark.usefixtures('engineer_on_t1')
    async def test_a_second_stop_after_the_block_is_let_through(
        self, harness: CompletionHarness
    ) -> None:
        first = await harness.stop()
        second = await harness.stop(active=True)
        assert (first.decision, second.output) == ('block', None)

    @pytest.mark.usefixtures('engineer_on_t1')
    @other_agent_cases()
    async def test_another_agent_type_is_let_through(
        self, agent_type: str | None, harness: CompletionHarness
    ) -> None:
        assert (await harness.stop(agent_type)).output is None

    @pytest.mark.usefixtures('engineer_on_t1')
    async def test_a_worker_that_started_nothing_is_let_through(
        self, harness: CompletionHarness
    ) -> None:
        assert (await harness.stop(ARCHITECT)).output is None


class TestCompletionGateOnTheIntern:
    @pytest.fixture
    async def intern_on_t1(self, harness: CompletionHarness) -> None:
        await harness.seed((INTERN_T1,))

    @pytest.mark.usefixtures('intern_on_t1')
    async def test_it_blocks_the_interns_stop_and_not_the_engineers(
        self, harness: CompletionHarness
    ) -> None:
        held = await harness.stop(INTERN)
        let_through = await harness.stop(ENGINEER)
        assert (held.decision, 'task-01.md is missing' in held.reason, let_through.output) == (
            'block',
            True,
            None,
        )

    @pytest.mark.usefixtures('intern_on_t1')
    async def test_with_a_done_half_naming_a_commit_it_lets_the_intern_stop(
        self, harness: CompletionHarness
    ) -> None:
        harness.write_brief(1, DONE_WITH_A_COMMIT)
        assert (await harness.stop(INTERN)).output is None


class TestWithoutState:
    async def test_with_no_ticket_recorded_it_is_let_through(
        self, harness: CompletionHarness
    ) -> None:
        reply = await harness.stop()
        assert (reply.output, harness.stderr.getvalue()) == (None, '')

    async def test_with_no_ticket_directory_it_is_let_through(
        self, harness: CompletionHarness
    ) -> None:
        await harness.seed((ENGINEER_T1,))
        harness.dispatch.checkout.joinpath('.mightymodels').rename(
            harness.checkout.joinpath('moved')
        )
        assert (await harness.stop()).output is None

    async def test_an_unreadable_database_is_let_through_and_says_why(
        self, harness: CompletionHarness
    ) -> None:
        harness.dispatch.data_directory.write_text('not a directory')
        reply = await harness.stop()
        assert reply.output is None
        assert harness.stderr.getvalue().startswith('mightymodels-hooks: completion-gate: ')
