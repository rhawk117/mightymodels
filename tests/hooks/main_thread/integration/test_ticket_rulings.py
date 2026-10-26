from typing import TYPE_CHECKING

import pytest

from tests.hooks.dispatch.dispatch_builders import SLUG, SeededTask
from tests.hooks.main_thread.main_thread_builders import (
    OTHER_SLUG,
    OUTSIDE_PATH,
    WORKER,
    edit_payload,
)

if TYPE_CHECKING:
    from tests.hooks.main_thread.main_thread_builders import MainThreadHarness


class TestWithoutATicketDirectory:
    async def test_edit_is_not_judged(self, harness: MainThreadHarness) -> None:
        verdict = await harness.verdict(edit_payload('Edit', OUTSIDE_PATH))
        assert verdict.decision is None


@pytest.mark.usefixtures('ticket_directory')
class TestWithATicket:
    @pytest.fixture
    def ticket_directory(self, harness: MainThreadHarness) -> None:
        harness.dispatch.make_ticket_directory()

    async def test_edit_with_no_ticket_recorded_is_not_judged(
        self, harness: MainThreadHarness
    ) -> None:
        verdict = await harness.verdict(edit_payload('Edit', OUTSIDE_PATH))
        assert verdict.decision is None

    async def test_edit_outside_the_ticket_directories_is_asked(
        self, harness: MainThreadHarness
    ) -> None:
        await harness.dispatch.seed((SeededTask(key='T1'),))
        verdict = await harness.verdict(edit_payload('Write', OUTSIDE_PATH))
        assert (verdict.decision, SLUG in verdict.detail) == ('ask', True)

    async def test_edit_inside_a_ticket_directory_is_not_judged(
        self, harness: MainThreadHarness
    ) -> None:
        await harness.dispatch.seed((SeededTask(key='T1'),))
        path = harness.checkout.joinpath('.mightymodels', str(SLUG), 'plan.md')
        verdict = await harness.verdict(edit_payload('Edit', str(path)))
        assert verdict.decision is None

    async def test_worker_edit_is_not_judged(self, harness: MainThreadHarness) -> None:
        await harness.dispatch.seed((SeededTask(key='T1'),))
        verdict = await harness.verdict(edit_payload('Edit', OUTSIDE_PATH, WORKER))
        assert verdict.decision is None

    async def test_edit_with_two_unclosed_tickets_is_a_warning(
        self, harness: MainThreadHarness
    ) -> None:
        await harness.dispatch.seed((SeededTask(key='T1'),))
        await harness.stage_other_ticket(OTHER_SLUG)
        verdict = await harness.verdict(edit_payload('Edit', OUTSIDE_PATH))
        assert (verdict.decision, str(OTHER_SLUG) in verdict.detail) == ('message', True)
