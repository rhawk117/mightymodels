"""Reading hook payloads from Claude Code's JSON, and the hook JSON written back."""

from pathlib import Path

import pytest
from python_harness.hooks.domain import BashCall, OtherToolCall, SessionStart
from python_harness.hooks.errors import (
    HookEventMismatchError,
    HookFieldMissingError,
    HookPayloadNotJsonError,
    HookPayloadNotObjectError,
)
from python_harness.hooks.schemas import (
    note_document,
    parse_hook_payload,
    parse_session_start,
    parse_tool_call,
    session_context_document,
)
from python_harness.hooks.tests.payloads import (
    bash_payload,
    session_payload,
    tool_payload,
)


class TestParsePayload:
    def test_text_that_is_not_json_is_refused(self) -> None:
        with pytest.raises(HookPayloadNotJsonError, match='not JSON: Expecting value'):
            parse_hook_payload('')

    @pytest.mark.parametrize(
        ('text', 'found'),
        [
            pytest.param('[]', 'array', id='array'),
            pytest.param('"x"', 'string', id='string'),
            pytest.param('1', 'number', id='number'),
            pytest.param('true', 'boolean', id='boolean'),
            pytest.param('null', 'null', id='null'),
        ],
    )
    def test_json_that_is_not_an_object_is_refused(self, text: str, found: str) -> None:
        with pytest.raises(HookPayloadNotObjectError, match=f'a JSON {found},'):
            parse_hook_payload(text)


class TestParseSessionStart:
    def test_cwd_is_read(self) -> None:
        payload = parse_hook_payload(session_payload('/work/p', source='compact'))

        assert parse_session_start(payload) == SessionStart(Path('/work/p'))

    def test_a_missing_cwd_falls_back_to_the_process_directory(self) -> None:
        payload = parse_hook_payload('{"hook_event_name": "SessionStart"}')

        assert parse_session_start(payload) == SessionStart(Path())

    def test_another_event_is_refused(self) -> None:
        payload = parse_hook_payload(bash_payload('ls'))

        with pytest.raises(HookEventMismatchError, match='SessionStart events, not Pre'):
            parse_session_start(payload)


class TestParseToolCall:
    def test_a_bash_call_carries_its_command(self) -> None:
        payload = parse_hook_payload(bash_payload('python x', cwd='/w'))

        assert parse_tool_call(payload) == BashCall('python x')

    def test_another_tool_is_named(self) -> None:
        payload = parse_hook_payload(tool_payload('Edit'))

        assert parse_tool_call(payload) == OtherToolCall('Edit')

    def test_a_bash_call_without_cwd_is_still_judged(self) -> None:
        payload = parse_hook_payload('{"tool_name": "Bash", "tool_input": {"command": "x"}}')

        assert parse_tool_call(payload) == BashCall('x')

    def test_a_bash_call_without_a_command_is_refused(self) -> None:
        text = '{"cwd": "/w", "tool_name": "Bash", "tool_input": {"command": 1}}'

        with pytest.raises(HookFieldMissingError, match=r"'tool_input\.command'"):
            parse_tool_call(parse_hook_payload(text))

    def test_another_event_is_refused(self) -> None:
        payload = parse_hook_payload(session_payload('/w'))

        with pytest.raises(HookEventMismatchError, match='PreToolUse events'):
            parse_tool_call(payload)


class TestDocuments:
    def test_the_session_document_carries_additional_context(self) -> None:
        assert session_context_document('facts') == {
            'hookSpecificOutput': {
                'hookEventName': 'SessionStart',
                'additionalContext': 'facts',
            }
        }

    def test_the_note_document_carries_additional_context_only(self) -> None:
        assert note_document('use uv') == {
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'additionalContext': 'use uv',
            }
        }
