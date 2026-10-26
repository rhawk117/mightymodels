from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import StateError
from mightymodels_hooks.branch_state import BranchTickets, Landing

from tests.hooks.dispatch.dispatch_builders import SLUG
from tests.hooks.main_thread.main_thread_builders import (
    OUTSIDE_PATH,
    PUSH,
    WORKER,
    FakeTicketOnBranch,
    bash_payload,
    edit_payload,
    judge,
    one_unclosed,
    several_unclosed,
)

if TYPE_CHECKING:
    from mightymodels_hooks.cli import HookPayload

UNREADABLE = StateError('the database is locked')


class TestEdits:
    @pytest.mark.parametrize('tool', ['Edit', 'Write'])
    async def test_edit_outside_the_ticket_directories_is_asked(self, tool: str) -> None:
        fake = FakeTicketOnBranch(tickets=one_unclosed())
        verdict = await judge(edit_payload(tool, OUTSIDE_PATH), fake)
        assert (verdict.decision, SLUG in verdict.detail, OUTSIDE_PATH in verdict.detail) == (
            'ask',
            True,
            True,
        )

    async def test_edit_inside_a_ticket_directory_reads_no_state(self) -> None:
        fake = FakeTicketOnBranch(in_directory=True, tickets=one_unclosed())
        verdict = await judge(edit_payload('Edit', '.mightymodels/x/plan.md'), fake)
        assert (verdict.decision, fake.reads) == (None, ['holds .mightymodels/x/plan.md'])

    async def test_edit_with_no_unclosed_ticket_is_not_judged(self) -> None:
        verdict = await judge(edit_payload('Edit', OUTSIDE_PATH), FakeTicketOnBranch())
        assert verdict.decision is None

    async def test_edit_with_several_unclosed_tickets_is_a_warning(self) -> None:
        fake = FakeTicketOnBranch(tickets=several_unclosed())
        verdict = await judge(edit_payload('Write', OUTSIDE_PATH), fake)
        assert (verdict.decision, '2 unclosed tickets' in verdict.detail) == ('message', True)

    async def test_edit_with_unreadable_tickets_goes_ahead_with_a_warning(self) -> None:
        fake = FakeTicketOnBranch(tickets=UNREADABLE)
        verdict = await judge(edit_payload('Edit', OUTSIDE_PATH), fake)
        assert (verdict.decision, 'locked' in verdict.detail) == ('message', True)


class TestPushes:
    async def test_push_is_denied_when_the_landing_cannot_be_read(self) -> None:
        verdict = await judge(bash_payload(PUSH), FakeTicketOnBranch(landing=UNREADABLE))
        assert (verdict.decision, 'locked' in verdict.detail) == ('deny', True)

    async def test_push_is_denied_while_items_are_unproven(self) -> None:
        landing = Landing(unclosed=(SLUG,), unproven=('T1 is blocked: stuck', 'T1.AC-1 failed'))
        verdict = await judge(bash_payload(PUSH), FakeTicketOnBranch(landing=landing))
        assert (verdict.decision, 'T1 is blocked: stuck; T1.AC-1 failed' in verdict.detail) == (
            'deny',
            True,
        )

    async def test_push_with_everything_proven_is_not_judged(self) -> None:
        landing = Landing(unclosed=(SLUG,))
        verdict = await judge(bash_payload(PUSH), FakeTicketOnBranch(landing=landing))
        assert verdict.decision is None

    async def test_push_with_several_unclosed_tickets_is_a_warning_not_a_denial(self) -> None:
        landing = Landing(unclosed=(SLUG, 'other-it'), unproven=('T1 is blocked',))
        verdict = await judge(bash_payload(PUSH), FakeTicketOnBranch(landing=landing))
        assert verdict.decision == 'message'

    async def test_command_that_pushes_nothing_reads_no_state(self) -> None:
        fake = FakeTicketOnBranch(landing=UNREADABLE)
        verdict = await judge(bash_payload('echo "git push"'), fake)
        assert (verdict.decision, fake.reads) == (None, [])


class TestCallers:
    @pytest.mark.parametrize(
        'payload',
        [edit_payload('Edit', OUTSIDE_PATH, WORKER), bash_payload(PUSH, WORKER)],
    )
    async def test_plugin_worker_passes_through_without_a_read(self, payload: HookPayload) -> None:
        fake = FakeTicketOnBranch(tickets=one_unclosed(), landing=UNREADABLE)
        verdict = await judge(payload, fake)
        assert (verdict.decision, fake.reads) == (None, [])

    @pytest.mark.parametrize(
        'payload',
        [
            {},
            {'tool_name': 'Read', 'tool_input': {'file_path': OUTSIDE_PATH}},
            {'tool_name': 'Edit', 'tool_input': 'text'},
            {'tool_name': 'Edit', 'tool_input': {'file_path': 3}},
            bash_payload(['git', 'push']),
        ],
    )
    async def test_payload_the_gate_does_not_cover_is_not_judged(
        self, payload: HookPayload
    ) -> None:
        fake = FakeTicketOnBranch(tickets=BranchTickets(unclosed=(SLUG,)), landing=UNREADABLE)
        verdict = await judge(payload, fake)
        assert verdict.decision is None
