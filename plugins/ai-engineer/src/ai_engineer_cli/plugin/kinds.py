from dataclasses import dataclass


@dataclass(frozen=True)
class KindSpec:
    """What one component kind builds: its builder skill, the files it writes and where.

    A `{name}` in a file or directory stands for the component name. A kind with no builder is
    written by hand in a short session, and one with no directory creates none because its file
    sits at the plugin root.
    """

    label: str
    builder: str | None
    directory: str | None
    files: tuple[str, ...]


KIND_SPECS: dict[str, KindSpec] = {
    'skill': KindSpec(
        label='skill',
        builder='create-skill',
        directory='skills/{name}',
        files=('skills/{name}/SKILL.md',),
    ),
    # A command is a skill with an argument hint, not a `commands/` file (PP-A7).
    'command': KindSpec(
        label='command',
        builder='create-skill',
        directory='skills/{name}',
        files=('skills/{name}/SKILL.md',),
    ),
    'agent': KindSpec(
        label='agent',
        builder='create-subagent',
        directory='agents',
        files=('agents/{name}.md',),
    ),
    'hook': KindSpec(
        label='hook',
        builder='create-hooks',
        directory='hooks',
        files=('hooks/hooks.json', 'scripts/{name}.py'),
    ),
    'mcp': KindSpec(
        label='MCP server',
        builder='create-mcp',
        directory='mcp/{name}',
        files=('.mcp.json', 'mcp/{name}/pyproject.toml', 'mcp/{name}/src/{package}/'),
    ),
    'lsp': KindSpec(
        label='LSP server',
        builder=None,
        directory=None,
        files=('.lsp.json',),
    ),
    'executable': KindSpec(
        label='executable',
        builder=None,
        directory='bin',
        files=('bin/{name}',),
    ),
    'output-style': KindSpec(
        label='output style',
        builder=None,
        directory='output-styles',
        files=('output-styles/{name}.md',),
    ),
}

# Kinds a Claude Code plugin cannot ship, mapped to the sentence that says where the guidance goes.
OUTSIDE_PLUGIN_KINDS: dict[str, str] = {
    'rule': (
        'a plugin cannot ship rules; record the guidance as an outside_plugin entry whose '
        'mechanism is a project rule file .claude/rules/<name>.md or CLAUDE.md'
    ),
    'extension': (
        'Claude Code has no extensions directory in a plugin; record the need as an '
        'outside_plugin entry, or use a hook, an MCP server or an executable'
    ),
}

RENAMED_KINDS: dict[str, str] = {'worker': 'agent'}
