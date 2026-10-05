"""Hook payloads read from Claude Code's event JSON, and the hook JSON written back."""

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType, NoneType
from typing import TypeIs

from python_harness.core.output import JsonValue
from python_harness.hooks.domain import (
    BashCall,
    HookEvent,
    OtherToolCall,
    SessionStart,
    ToolCall,
)
from python_harness.hooks.errors import (
    HookEventMismatchError,
    HookFieldMissingError,
    HookPayloadNotJsonError,
    HookPayloadNotObjectError,
)

type HookPayload = Mapping[str, object]

BASH_TOOL = 'Bash'
CWD_FIELD = 'cwd'
EVENT_FIELD = 'hook_event_name'
EMPTY_PAYLOAD: HookPayload = MappingProxyType({})
JSON_TYPE_NAMES: Mapping[type, str] = MappingProxyType(
    {
        list: 'array',
        str: 'string',
        int: 'number',
        float: 'number',
        bool: 'boolean',
        NoneType: 'null',
    }
)


def describe_json_type(value: object) -> str:
    return JSON_TYPE_NAMES.get(type(value), type(value).__name__)


def decode_payload(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise HookPayloadNotJsonError(error.msg) from error


def is_json_object(value: object) -> TypeIs[HookPayload]:
    return isinstance(value, Mapping)


def parse_hook_payload(text: str) -> HookPayload:
    document = decode_payload(text)
    if not is_json_object(document):
        raise HookPayloadNotObjectError(describe_json_type(document))
    return MappingProxyType(document)


def read_string_field(payload: HookPayload, name: str, *, label: str | None = None) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise HookFieldMissingError(name if label is None else label)
    return value


def read_table_field(payload: HookPayload, name: str) -> HookPayload:
    value = payload.get(name)
    if is_json_object(value):
        return value
    return EMPTY_PAYLOAD


def find_unexpected_event(payload: HookPayload, expected: HookEvent) -> str | None:
    found = payload.get(EVENT_FIELD, expected.value)
    if found == expected.value:
        return None
    return str(found)


def require_event(payload: HookPayload, expected: HookEvent) -> None:
    found = find_unexpected_event(payload, expected)
    if found is not None:
        raise HookEventMismatchError(expected.value, found)


def parse_cwd(payload: HookPayload) -> Path:
    cwd = payload.get(CWD_FIELD)
    if not isinstance(cwd, str):
        return Path()
    return Path(cwd)


def parse_session_start(payload: HookPayload) -> SessionStart:
    require_event(payload, HookEvent.SESSION_START)
    return SessionStart(cwd=parse_cwd(payload))


def parse_tool_call(payload: HookPayload) -> ToolCall:
    require_event(payload, HookEvent.PRE_TOOL_USE)
    tool_name = read_string_field(payload, 'tool_name')
    if tool_name != BASH_TOOL:
        return OtherToolCall(tool_name)
    tool_input = read_table_field(payload, 'tool_input')
    command = read_string_field(tool_input, 'command', label='tool_input.command')
    return BashCall(command=command)


def context_document(event: HookEvent, context: str) -> JsonValue:
    return {
        'hookSpecificOutput': {
            'hookEventName': event.value,
            'additionalContext': context,
        }
    }
