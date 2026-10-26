from typing import TYPE_CHECKING

import pytest

from tests.hooks.pointer.pointer_builders import pointer_payload

if TYPE_CHECKING:
    from tests.hooks.pointer.pointer_builders import PointerHarness


def target_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('tool', 'tool_input', 'kind', 'key'),
        [
            pytest.param('task_start', {'slug': 'port-it'}, 'ticket', 'port-it', id='slug'),
            pytest.param('crashout_add', {'ticket': 'port-it'}, 'ticket', 'port-it', id='ticket'),
            pytest.param(
                'investigation_add',
                {'investigation_id': 'inv-1'},
                'investigation',
                'inv-1',
                id='id',
            ),
        ],
    )


def silent_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('tool', 'tool_input'),
        [
            pytest.param('investigation_start', {'title': 'x'}, id='investigation-start'),
            pytest.param('task_start', {}, id='no-slug'),
            pytest.param('review_start', {'slug': None}, id='null-slug'),
            pytest.param('task_start', None, id='no-input'),
        ],
    )


class TestPointerWrites:
    @target_cases()
    async def test_a_call_points_the_session_at_what_it_names(
        self, harness: PointerHarness, tool: str, tool_input: object, kind: str, key: str
    ) -> None:
        output = await harness.point(pointer_payload(tool, tool_input))
        found = await harness.pointer()
        assert output is None
        assert found is not None
        assert (found.kind, found.key) == (kind, key)
        assert harness.stderr.getvalue() == ''

    async def test_the_latest_call_wins(self, harness: PointerHarness) -> None:
        await harness.point(pointer_payload('task_start', {'slug': 'port-it'}))
        await harness.point(pointer_payload('investigation_add', {'investigation_id': 'inv-1'}))
        found = await harness.pointer()
        assert found is not None
        assert (found.kind, found.key) == ('investigation', 'inv-1')

    @pytest.mark.parametrize('session_id', [None, ''])
    async def test_a_payload_without_a_session_id_writes_nothing(
        self, harness: PointerHarness, session_id: object
    ) -> None:
        payload = pointer_payload('task_start', {'slug': 'port-it'}, session_id=session_id)
        output = await harness.point(payload)
        assert output is None
        assert await harness.pointer() is None

    @silent_cases()
    async def test_a_call_naming_nothing_writes_nothing(
        self, harness: PointerHarness, tool: str, tool_input: object
    ) -> None:
        output = await harness.point(pointer_payload(tool, tool_input))
        assert output is None
        assert await harness.pointer() is None
        assert harness.stderr.getvalue() == ''

    async def test_a_repository_with_no_ticket_directory_writes_nothing(
        self, harness: PointerHarness
    ) -> None:
        harness.checkout.joinpath('.mightymodels', 'port-it').rmdir()
        output = await harness.point(pointer_payload('task_start', {'slug': 'port-it'}))
        assert output is None
        assert await harness.pointer() is None
