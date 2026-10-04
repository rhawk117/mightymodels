from typing import Literal

import msgspec
from msgspec import UNSET, UnsetType

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


class MatcherGroup(msgspec.Struct, frozen=True, kw_only=True):
    hooks: list[object]
    matcher: str | UnsetType = UNSET


class HookBase(
    msgspec.Struct,
    frozen=True,
    kw_only=True,
    forbid_unknown_fields=True,
    rename={
        'if_': 'if',
        'status_message': 'statusMessage',
        'async_': 'async',
        'async_rewake': 'asyncRewake',
        'allowed_env_vars': 'allowedEnvVars',
    },
):
    if_: str | UnsetType = UNSET
    timeout: int | float | UnsetType = UNSET
    status_message: str | UnsetType = UNSET
    once: bool = False


class CommandHook(HookBase, frozen=True, tag='command', tag_field='type'):
    command: str
    args: list[str] | UnsetType = UNSET
    async_: bool = False
    async_rewake: bool = False
    shell: Literal['bash', 'powershell'] | UnsetType = UNSET


class HttpHook(HookBase, frozen=True, tag='http', tag_field='type'):
    url: str
    headers: dict[str, str] = {}
    allowed_env_vars: list[str] = []


class McpToolHook(HookBase, frozen=True, tag='mcp_tool', tag_field='type'):
    server: str
    tool: str
    input: dict[str, object] = {}


class PromptHook(HookBase, frozen=True, tag='prompt', tag_field='type'):
    prompt: str
    model: str | UnsetType = UNSET


class AgentHook(HookBase, frozen=True, tag='agent', tag_field='type'):
    prompt: str
    model: str | UnsetType = UNSET


type HookHandler = CommandHook | HttpHook | McpToolHook | PromptHook | AgentHook
