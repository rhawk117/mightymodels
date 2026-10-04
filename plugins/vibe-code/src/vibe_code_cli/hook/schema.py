from typing import Literal

import msgspec
from msgspec import UNSET, UnsetType

# The events of the event table in the hooks reference (hooks.md:39-71).
EventName = Literal[
    'SessionStart',
    'Setup',
    'UserPromptSubmit',
    'UserPromptExpansion',
    'PreToolUse',
    'PermissionRequest',
    'PermissionDenied',
    'PostToolUse',
    'PostToolUseFailure',
    'PostToolBatch',
    'Notification',
    'MessageDisplay',
    'SubagentStart',
    'SubagentStop',
    'TaskCreated',
    'TaskCompleted',
    'Stop',
    'StopFailure',
    'TeammateIdle',
    'InstructionsLoaded',
    'ConfigChange',
    'CwdChanged',
    'DirectoryAdded',
    'FileChanged',
    'WorktreeCreate',
    'WorktreeRemove',
    'PreCompact',
    'PostCompact',
    'PreModelSwitch',
    'PostModelSwitch',
    'Elicitation',
    'ElicitationResult',
    'SessionEnd',
]

FIELD_NAMES = {
    'if_': 'if',
    'status_message': 'statusMessage',
    'async_': 'async',
    'async_rewake': 'asyncRewake',
    'allowed_env_vars': 'allowedEnvVars',
}


class MatcherGroup(msgspec.Struct):
    """A matcher group, the object in an event's array (hooks.md:240-241, 287-289, 402-404).

    Its handlers stay raw so that each one is converted, and reported, on its own.
    """

    hooks: list[object]
    matcher: str | UnsetType = UNSET


class HookBase(msgspec.Struct, kw_only=True, forbid_unknown_fields=True, rename=FIELD_NAMES):
    """The common fields of every handler type (hooks.md:418-428)."""

    if_: str | UnsetType = UNSET
    timeout: int | float | UnsetType = UNSET
    status_message: str | UnsetType = UNSET
    once: bool = False


class CommandHook(HookBase, tag='command', tag_field='type'):
    """A command hook (hooks.md:446-456)."""

    command: str
    args: list[str] | UnsetType = UNSET
    async_: bool = False
    async_rewake: bool = False
    shell: Literal['bash', 'powershell'] | UnsetType = UNSET


class HttpHook(HookBase, tag='http', tag_field='type'):
    """An HTTP hook (hooks.md:501-509)."""

    url: str
    headers: dict[str, str] = {}
    allowed_env_vars: list[str] = []


class McpToolHook(HookBase, tag='mcp_tool', tag_field='type'):
    """An MCP tool hook (hooks.md:540-548); `input` holds the tool's own arguments."""

    server: str
    tool: str
    input: dict[str, object] = {}


class PromptHook(HookBase, tag='prompt', tag_field='type'):
    """A prompt hook (hooks.md:586-593)."""

    prompt: str
    model: str | UnsetType = UNSET


class AgentHook(HookBase, tag='agent', tag_field='type'):
    """An agent hook, which takes the prompt hook's fields (hooks.md:586-593)."""

    prompt: str
    model: str | UnsetType = UNSET


type HookHandler = CommandHook | HttpHook | McpToolHook | PromptHook | AgentHook
