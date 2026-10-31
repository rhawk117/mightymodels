from typing import TYPE_CHECKING

import pytest

from tests.core.git.git_builders import commit_file
from tests.hooks.dispatch.dispatch_builders import SeededTask
from tests.hooks.main_thread.main_thread_builders import (
    OTHER_SLUG,
    PUSH,
    WORKER,
    bash_payload,
)

VERIFIED = SeededTask(key='T1', status='verified')

if TYPE_CHECKING:
    from tests.hooks.main_thread.main_thread_builders import MainThreadHarness


class TestWithoutATicketDirectory:
    async def test_push_is_not_judged(self, harness: MainThreadHarness) -> None:
        verdict = await harness.verdict(bash_payload(PUSH))
        assert verdict.decision is None


@pytest.mark.usefixtures('ticket_directory')
class TestWithATicket:
    @pytest.fixture
    def ticket_directory(self, harness: MainThreadHarness) -> None:
        harness.dispatch.make_ticket_directory()

    async def test_push_with_no_ticket_recorded_is_not_judged(
        self, harness: MainThreadHarness
    ) -> None:
        verdict = await harness.verdict(bash_payload(PUSH))
        assert verdict.decision is None

    async def test_push_is_denied_while_a_task_is_unverified(
        self, harness: MainThreadHarness
    ) -> None:
        await harness.dispatch.seed((SeededTask(key='T1'),))
        verdict = await harness.verdict(bash_payload(PUSH))
        assert (verdict.decision, 'T1 is in-progress' in verdict.detail) == ('deny', True)

    async def test_push_is_denied_without_a_receipt_at_head(
        self, harness: MainThreadHarness
    ) -> None:
        head = await commit_file(harness.checkout, 'a.txt')
        await harness.dispatch.seed((VERIFIED,))
        await harness.prove(head, 'landing')
        await commit_file(harness.checkout, 'b.txt')
        verdict = await harness.verdict(bash_payload(PUSH))
        assert (verdict.decision, 'no receipt at the current HEAD' in verdict.detail) == (
            'deny',
            True,
        )

    async def test_push_of_a_proven_landing_is_not_judged(self, harness: MainThreadHarness) -> None:
        head = await commit_file(harness.checkout, 'a.txt')
        await harness.dispatch.seed((VERIFIED,))
        await harness.prove(head, 'landing')
        verdict = await harness.verdict(bash_payload(PUSH))
        assert verdict.decision is None

    async def test_worker_push_is_not_judged(self, harness: MainThreadHarness) -> None:
        await harness.dispatch.seed((SeededTask(key='T1'),))
        verdict = await harness.verdict(bash_payload(PUSH, WORKER))
        assert verdict.decision is None

    async def test_push_with_two_unclosed_tickets_is_a_warning(
        self, harness: MainThreadHarness
    ) -> None:
        await harness.dispatch.seed((SeededTask(key='T1'),))
        await harness.stage_other_ticket(OTHER_SLUG)
        verdict = await harness.verdict(bash_payload(PUSH))
        assert verdict.decision == 'message'

    async def test_push_is_denied_when_the_state_cannot_be_read(
        self, harness: MainThreadHarness
    ) -> None:
        harness.dispatch.data_directory.write_text('not a directory')
        verdict = await harness.verdict(bash_payload(PUSH))
        assert verdict.decision == 'deny'


@pytest.mark.usefixtures('ticket_directory')
class TestLandingRule:
    @pytest.fixture
    def ticket_directory(self, harness: MainThreadHarness) -> None:
        harness.dispatch.make_ticket_directory()

    async def test_push_of_a_pass_at_head_in_the_task_phase_is_not_judged(
        self, harness: MainThreadHarness
    ) -> None:
        head = await commit_file(harness.checkout, 'a.txt')
        await harness.dispatch.seed((VERIFIED,))
        await harness.prove(head, 'task')
        verdict = await harness.verdict(bash_payload(PUSH))
        assert verdict.decision is None

    async def test_push_is_denied_when_the_contract_has_only_an_integration_command(
        self, harness: MainThreadHarness
    ) -> None:
        head = await commit_file(harness.checkout, 'a.txt')
        await harness.dispatch.seed((VERIFIED,))
        await harness.prove(head, 'landing', key='I1')
        verdict = await harness.verdict(bash_payload(PUSH))
        assert (verdict.decision, 'no live L* command' in verdict.detail) == ('deny', True)

    async def test_push_ignores_a_retired_command_without_a_receipt(
        self, harness: MainThreadHarness
    ) -> None:
        head = await commit_file(harness.checkout, 'a.txt')
        await harness.dispatch.seed((VERIFIED,))
        await harness.prove(head, 'landing')
        await harness.add_retired_command('L2', head)
        verdict = await harness.verdict(bash_payload(PUSH))
        assert verdict.decision is None
