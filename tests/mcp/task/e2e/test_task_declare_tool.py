from typing import TYPE_CHECKING

import pytest
from mightymodels_hooks.session_pointer import PointerTarget, pointer_target_of

from tests.hooks.pointer.pointer_builders import pointer_payload
from tests.mcp.server.server_harness import view_of
from tests.mcp.task.task_harness import OWNED, RecordingOpener, TaskHarness
from tests.mcp.ticket.ticket_harness import ANSWERED, SLUG, TicketHarness

if TYPE_CHECKING:
    from tests.mcp.server.server_harness import ServerHarness

DECLARE = {'slug': SLUG, 'task_ids': ['T2', 'T1']}


@pytest.fixture
async def staged(server_harness: ServerHarness) -> TaskHarness:
    tickets = TicketHarness(server=server_harness)
    view_of(await tickets.call('ticket_write', dict(ANSWERED)))
    view_of(await tickets.call('ticket_validate', {'slug': SLUG}))
    opener = RecordingOpener(inner=server_harness.dependencies.state)
    return TaskHarness(server=server_harness, opener=opener)


class TestTaskDeclare:
    async def test_writes_the_ids_as_pending(self, staged: TaskHarness) -> None:
        view = view_of(await staged.call('task_declare', DECLARE))

        assert [(task['id'], task['status']) for task in view['tasks']] == [
            ('T1', 'pending'),
            ('T2', 'pending'),
        ]
        assert view['advanced']
        assert staged.git_calls == []

    async def test_leaves_an_existing_task_unchanged(self, staged: TaskHarness) -> None:
        await staged.commit('first')
        start = {'slug': SLUG, 'task_id': 'T1', 'by': 'engineer', 'owned': [OWNED]}
        view_of(await staged.call('task_start', {**start, 'acceptance': ['AC-1']}))

        view = view_of(await staged.call('task_declare', DECLARE))

        assert [(task['id'], task['status']) for task in view['tasks']] == [
            ('T1', 'in-progress'),
            ('T2', 'pending'),
        ]

    @pytest.mark.parametrize('task_id', ['R1', 'C1'])
    async def test_refuses_a_residual_or_ci_id(self, staged: TaskHarness, task_id: str) -> None:
        result = await staged.call('task_declare', {'slug': SLUG, 'task_ids': [task_id]})

        assert result.is_error
        assert task_id in str(result.content)

    async def test_refuses_no_ids(self, staged: TaskHarness) -> None:
        assert (await staged.call('task_declare', {'slug': SLUG, 'task_ids': []})).is_error

    def test_points_the_session_at_the_ticket(self) -> None:
        target = pointer_target_of(pointer_payload('task_declare', {'slug': SLUG}))

        assert target == PointerTarget(kind='ticket', key=SLUG)
