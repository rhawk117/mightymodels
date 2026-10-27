import pytest
from mightymodels_hooks.session_pointer import PointerTarget, pointer_target_of

from tests.hooks.pointer.pointer_builders import pointer_payload


def unlisted_tool_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('tool', ['investigation_start', 'Write', 'unknown'])


def blank_field_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('value', [None, '', '  ', 7])


class TestPointerTargetOf:
    def test_a_slug_names_a_ticket(self) -> None:
        target = pointer_target_of(pointer_payload('task_show', {'slug': 'port-it'}))
        assert target == PointerTarget(kind='ticket', key='port-it')

    def test_a_ticket_field_names_a_ticket(self) -> None:
        target = pointer_target_of(pointer_payload('crashout_add', {'ticket': 'port-it'}))
        assert target == PointerTarget(kind='ticket', key='port-it')

    def test_an_investigation_id_names_an_investigation(self) -> None:
        payload = pointer_payload('investigation_knowns', {'investigation_id': 'inv-1'})
        assert pointer_target_of(payload) == PointerTarget(kind='investigation', key='inv-1')

    def test_the_tool_is_the_part_after_the_last_separator(self) -> None:
        payload = pointer_payload('task_show', {'slug': 'a'}, tool_name='x__y__task_show')
        assert pointer_target_of(payload) == PointerTarget(kind='ticket', key='a')

    @unlisted_tool_cases()
    def test_a_tool_outside_the_list_names_nothing(self, tool: str) -> None:
        assert pointer_target_of(pointer_payload(tool, {'slug': 'port-it'})) is None

    @blank_field_cases()
    def test_a_blank_or_mistyped_field_names_nothing(self, value: object) -> None:
        assert pointer_target_of(pointer_payload('task_show', {'slug': value})) is None

    def test_a_payload_without_a_tool_name_names_nothing(self) -> None:
        payload = pointer_payload('task_show', {'slug': 'a'}, tool_name=None)
        assert pointer_target_of(payload) is None
