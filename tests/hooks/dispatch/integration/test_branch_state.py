from typing import TYPE_CHECKING

import pytest
from mightymodels_hooks.hook_context import create_hook_context_at

from tests.hooks.dispatch.dispatch_builders import SLUG, SeededTask

if TYPE_CHECKING:
    from tests.hooks.dispatch.dispatch_builders import DispatchHarness

ENGINEER = 'mightymodels:workers:engineer'
ARCHITECT = 'mightymodels:workers:architect'
INTERN = 'mightymodels:workers:intern'


class TestWithoutATicketDirectory:
    async def test_main_thread_engineer_dispatch_is_not_judged(
        self, harness: DispatchHarness
    ) -> None:
        verdict = await harness.verdict(ENGINEER)
        assert verdict.decision is None

    async def test_intern_dispatch_is_denied_for_want_of_a_started_task(
        self, harness: DispatchHarness
    ) -> None:
        verdict = await harness.verdict(INTERN)
        assert verdict.decision == 'deny'


@pytest.mark.usefixtures('ticket_directory')
class TestWithATicket:
    @pytest.fixture
    def ticket_directory(self, harness: DispatchHarness) -> None:
        harness.make_ticket_directory()

    async def test_engineer_is_denied_while_no_task_is_in_progress(
        self, harness: DispatchHarness
    ) -> None:
        await harness.seed((SeededTask(key='T1', status='blocked', reasons=('stuck',)),))
        verdict = await harness.verdict(ENGINEER)
        assert (verdict.decision, SLUG in verdict.detail) == ('deny', True)

    async def test_engineer_is_let_through_with_a_task_in_progress(
        self, harness: DispatchHarness
    ) -> None:
        await harness.seed((SeededTask(key='T1'),))
        verdict = await harness.verdict(ENGINEER)
        assert verdict.decision is None

    async def test_architect_and_wingman_are_not_judged_during_a_block(
        self, harness: DispatchHarness
    ) -> None:
        tasks = (SeededTask(key='T1'), SeededTask(key='T2', status='blocked', reasons=('stuck',)))
        await harness.seed(tasks)
        verdicts = [await harness.verdict(target) for target in (ARCHITECT, 'wingman')]
        assert [verdict.decision for verdict in verdicts] == [None, None]

    async def test_intern_with_one_owned_file_is_let_through(
        self, harness: DispatchHarness
    ) -> None:
        await harness.seed((SeededTask(key='T1', worker='intern'),))
        verdict = await harness.verdict(INTERN)
        assert verdict.decision is None

    async def test_intern_with_two_owned_files_is_denied(self, harness: DispatchHarness) -> None:
        owned = ('src/a.py', 'src/b.py')
        await harness.seed((SeededTask(key='T1', worker='intern', owned=owned),))
        verdict = await harness.verdict(INTERN)
        assert (verdict.decision, 'T1 owns 2 files' in verdict.detail) == ('deny', True)

    async def test_unrecorded_repository_holds_no_ticket(self, harness: DispatchHarness) -> None:
        verdict = await harness.verdict(ENGINEER)
        assert verdict.decision is None


class TestTicketDirectory:
    async def test_ticket_directory_holds_the_files_below_it(
        self, harness: DispatchHarness
    ) -> None:
        context = create_hook_context_at({}, str(harness.checkout))
        inside = f'.mightymodels/{SLUG}/ticket.yml'
        assert (
            context.ticket_directory_holds(inside),
            context.ticket_directory_holds('.mightymodels/archives/a/t.yml'),
            context.ticket_directory_holds('src/a.py'),
            context.ticket_directory_holds('a\0b'),
        ) == (True, False, False, False)
