import re

# Built-in tool names from the tool table in https://code.claude.com/docs/en/tools-reference
# (docs snapshot 2026-10-03, tools-reference.md lines 21-66), plus `Task`, the old name of `Agent`
# that https://code.claude.com/docs/en/sub-agents says still works as an alias. Refresh this set
# from that table when the docs gain a tool.
KNOWN_TOOLS = frozenset(
    {
        'Agent',
        'Artifact',
        'AskUserQuestion',
        'Bash',
        'CronCreate',
        'CronDelete',
        'CronList',
        'Edit',
        'EndConversation',
        'EnterPlanMode',
        'EnterWorktree',
        'ExitPlanMode',
        'ExitWorktree',
        'Glob',
        'Grep',
        'ListAgents',
        'ListMcpResourcesTool',
        'LSP',
        'Monitor',
        'NotebookEdit',
        'PowerShell',
        'PushNotification',
        'Read',
        'ReadMcpResourceTool',
        'RemoteTrigger',
        'ReportFindings',
        'ScheduleWakeup',
        'SendFeedback',
        'SendMessage',
        'SendUserFile',
        'ShareOnboardingGuide',
        'Skill',
        'SubagentHandback',
        'Task',
        'TaskCreate',
        'TaskGet',
        'TaskList',
        'TaskOutput',
        'TaskStop',
        'TaskUpdate',
        'TodoWrite',
        'ToolSearch',
        'WaitForMcpServers',
        'WebFetch',
        'WebSearch',
        'Workflow',
        'Write',
    }
)
# `mcp__<server>`, `mcp__<server>__<tool>`, `mcp__<server>__*` and `mcp__*`, as in the sub-agents
# page under "Available tools".
MCP_TOOL = re.compile(r'mcp__[\w.*-]+')
COMMA_OUTSIDE_PARENTHESES = re.compile(r'(?:[^,(]|\([^)]*\))+')


def tool_entries(value: str | list[str] | None) -> list[str] | None:
    """The entries of a `tools` or `disallowedTools` value; None when the key is not set."""
    if isinstance(value, str):
        entries = COMMA_OUTSIDE_PARENTHESES.findall(value)
    elif isinstance(value, list):
        entries = value
    else:
        return None
    return [entry.strip() for entry in entries if entry.strip()]


def tool_name(entry: str) -> str:
    """The tool an entry names, without its specifier: `Bash(git *)` is `Bash`."""
    return entry.split('(', 1)[0].strip()


def is_known_tool(entry: str) -> bool:
    name = tool_name(entry)
    return name in KNOWN_TOOLS or MCP_TOOL.fullmatch(name) is not None
