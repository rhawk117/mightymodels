"""The JSON Claude Code writes to a hook's standard input, one frozen Struct per hook event.

Each Struct is tagged on `hook_event_name`, so a payload that names another event does not decode.
Fields Claude Code may leave out are optional and fields the hooks do not read are ignored.
"""

import msgspec

from mightymodels_hooks.workers import PLUGIN_PREFIX


class SessionStartPayload(
    msgspec.Struct, frozen=True, kw_only=True, tag_field='hook_event_name', tag='SessionStart'
):
    session_id: str | None = None
    cwd: str | None = None


class PreToolUsePayload(
    msgspec.Struct, frozen=True, kw_only=True, tag_field='hook_event_name', tag='PreToolUse'
):
    session_id: str | None = None
    cwd: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, object] | None = None
    agent_type: str | None = None


class PostToolUsePayload(
    msgspec.Struct, frozen=True, kw_only=True, tag_field='hook_event_name', tag='PostToolUse'
):
    session_id: str | None = None
    cwd: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, object] | None = None
    tool_response: object = None
    agent_type: str | None = None
    agent_id: str | None = None


class SubagentStopPayload(
    msgspec.Struct, frozen=True, kw_only=True, tag_field='hook_event_name', tag='SubagentStop'
):
    session_id: str | None = None
    cwd: str | None = None
    agent_type: str | None = None
    agent_id: str | None = None
    stop_hook_active: bool | None = None
    last_assistant_message: str | None = None


class PreCompactPayload(
    msgspec.Struct, frozen=True, kw_only=True, tag_field='hook_event_name', tag='PreCompact'
):
    session_id: str | None = None
    cwd: str | None = None


def plugin_caller_of(agent_type: str | None) -> str | None:
    return agent_type if agent_type is not None and agent_type.startswith(PLUGIN_PREFIX) else None


type HookEventPayload = (
    SessionStartPayload
    | PreToolUsePayload
    | PostToolUsePayload
    | SubagentStopPayload
    | PreCompactPayload
)
