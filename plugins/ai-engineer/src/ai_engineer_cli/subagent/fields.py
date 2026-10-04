import re

from ai_engineer_cli.findings import Finding, error, warning
from ai_engineer_cli.subagent.tools import is_known_tool, tool_entries, tool_name

# The 18 keys in the frontmatter table of https://code.claude.com/docs/en/sub-agents (docs
# snapshot 2026-10-03, sub-agents.md lines 303-320), including `omitClaudeMd`, `initialPrompt`
# and `experimental`. Refresh this set from that table when the docs gain a key.
KNOWN_KEYS = frozenset(
    {
        'name',
        'description',
        'tools',
        'disallowedTools',
        'model',
        'permissionMode',
        'maxTurns',
        'skills',
        'mcpServers',
        'hooks',
        'memory',
        'background',
        'omitClaudeMd',
        'effort',
        'isolation',
        'color',
        'initialPrompt',
        'experimental',
    }
)
# The "Ignored fields" line of https://code.claude.com/docs/en/plugins/components.
PLUGIN_IGNORED_KEYS = ('permissionMode', 'hooks', 'mcpServers', 'initialPrompt')
NAME_PATTERN = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
MODEL_PATTERN = re.compile(r'(?:sonnet|opus|haiku|fable)(?:\[1m\])?|inherit')
TRIGGER_PATTERN = re.compile(
    r'\b(use (this )?(skill |agent )?(when|after|proactively)|trigger when|'
    r'invoke when|call (this|it) when)\b',
    re.IGNORECASE,
)


def check_fields(fields: dict[str, object], *, plugin: bool, unquoted_colon: bool) -> list[Finding]:
    return [
        *check_name(fields, plugin=plugin),
        *check_description(fields, unquoted_colon=unquoted_colon),
        *check_tools(fields),
        *check_model(fields),
        *check_unknown_keys(fields),
        *check_permission_mode(fields, plugin=plugin),
    ]


def check_name(fields: dict[str, object], *, plugin: bool) -> list[Finding]:
    name = fields.get('name')
    if isinstance(name, str) and name.strip():
        return check_name_value(name)
    if plugin:
        return [warning('name is missing or empty; a plugin agent loads under its filename')]
    return [error('name is missing or empty; Claude Code skips the file as documentation')]


def check_name_value(name: str) -> list[Finding]:
    if NAME_PATTERN.fullmatch(name):
        return []
    return [
        error(
            f'name {name!r} must be lowercase letters, digits and single hyphens, with no '
            "':' (reserved for plugin-scoped names) and no leading hyphen"
        )
    ]


def check_description(fields: dict[str, object], *, unquoted_colon: bool) -> list[Finding]:
    description = fields.get('description')
    if not isinstance(description, str) or not description.strip():
        return []  # the built-in warns about a missing description
    findings: list[Finding] = []
    if not TRIGGER_PATTERN.search(description):
        findings.append(
            warning(
                'description states a capability but no trigger condition; add '
                "'Use when ...' so Claude knows when to delegate to this agent"
            )
        )
    if unquoted_colon:
        findings.append(
            warning(
                "description contains ':' and is not quoted in the source; quote it "
                'so a YAML reader cannot misparse it'
            )
        )
    return findings


def check_tools(fields: dict[str, object]) -> list[Finding]:
    entries = tool_entries(fields.get('tools'))
    if entries is None:
        return [
            warning(
                "no 'tools' list, so the agent inherits every tool the session has; "
                'list the tools it needs'
            )
        ]
    if not entries:
        return []  # an empty list launches the agent with no tools (errors page)
    return [
        *check_tool_names(entries),
        *check_denylist(fields),
        *check_turn_budget(entries, fields),
    ]


def check_tool_names(entries: list[str]) -> list[Finding]:
    return [
        error(
            f'{entry!r} is not a Claude Code tool name or an mcp__<server> or '
            'mcp__<server>__<tool> reference'
        )
        for entry in entries
        if not is_known_tool(entry)
    ]


def check_denylist(fields: dict[str, object]) -> list[Finding]:
    if 'disallowedTools' not in fields:
        return []
    return [
        warning(
            "'disallowedTools' is applied first and 'tools' is then resolved against the "
            'remaining pool, so a tool in both is removed; setting both rarely does what it '
            'looks like'
        )
    ]


def check_turn_budget(entries: list[str], fields: dict[str, object]) -> list[Finding]:
    if 'Bash' not in map(tool_name, entries) or 'maxTurns' in fields:
        return []
    return [
        warning('agent can run commands but sets no maxTurns; a runaway delegation has no stop')
    ]


def check_model(fields: dict[str, object]) -> list[Finding]:
    model = fields.get('model')
    if not isinstance(model, str) or MODEL_PATTERN.fullmatch(model) or '-' in model:
        return []
    return [
        error(
            f'model {model!r} is not a Claude Code alias (sonnet, opus, haiku, fable), '
            "'inherit', or a full model ID"
        )
    ]


def check_unknown_keys(fields: dict[str, object]) -> list[Finding]:
    return [
        warning(f'{key!r} is not a documented frontmatter key; Claude Code ignores it')
        for key in sorted(set(fields) - KNOWN_KEYS)
    ]


def check_permission_mode(fields: dict[str, object], *, plugin: bool) -> list[Finding]:
    if plugin:
        return [
            warning(f'{key!r} is ignored in a plugin agents/ directory; Claude Code drops it')
            for key in PLUGIN_IGNORED_KEYS
            if key in fields
        ]
    if fields.get('permissionMode') != 'bypassPermissions':
        return []
    return [
        warning(
            "a subagent that declares bypassPermissions keeps the main conversation's "
            'permission mode instead (v2.1.267 or later), so the setting does not skip prompts'
        )
    ]
