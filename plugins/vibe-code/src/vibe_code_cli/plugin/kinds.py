from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(slots=True, kw_only=True, frozen=True)
class KindSpec:
    label: str
    builder: str | None
    directory: str | None
    files: tuple[str, ...]
    opener: str
    reference: str | None


class Kind(StrEnum):
    SKILL = 'skill'
    COMMAND = 'command'
    AGENT = 'agent'
    HOOK = 'hook'
    MCP = 'mcp'
    LSP = 'lsp'
    EXECUTABLE = 'executable'
    OUTPUT_STYLE = 'output-style'


class OutsideKind(StrEnum):
    RULE = 'rule'
    EXTENSION = 'extension'


def kind_specs() -> dict[str, KindSpec]:
    return {
        Kind.SKILL: KindSpec(
            label='skill',
            builder='create-skill',
            directory='skills/{name}',
            files=('skills/{name}/SKILL.md',),
            opener=('Create the `{name}` skill for the plugin at {root}: {purpose}'),
            reference='references/skills.md',
        ),
        Kind.COMMAND: KindSpec(
            label='command',
            builder='create-skill',
            directory='skills/{name}',
            files=('skills/{name}/SKILL.md',),
            opener=(
                'Create `{name}` as a user-invocable skill with an argument-hint for the plugin at '
                '{root}: {purpose}'
            ),
            reference='references/commands.md',
        ),
        Kind.AGENT: KindSpec(
            label='agent',
            builder='create-subagent',
            directory='agents',
            files=('agents/{name}.md',),
            opener=(
                'Create the `{name}` agent for the plugin at {root}; it does one thing: {purpose}'
            ),
            reference='references/agents.md',
        ),
        Kind.HOOK: KindSpec(
            label='hook',
            builder='create-hooks',
            directory='hooks',
            files=('hooks/hooks.json', 'scripts/{name}.py'),
            opener=('Create the `{name}` hook for the plugin at {root}: {purpose}'),
            reference='references/hooks.md',
        ),
        Kind.MCP: KindSpec(
            label='MCP server',
            builder='create-mcp',
            directory='mcp/{name}',
            files=('.mcp.json', 'mcp/{name}/pyproject.toml', 'mcp/{name}/src/{package}/'),
            opener=('Create the `{name}` MCP server for the plugin at {root}: {purpose}'),
            reference='references/mcp.md',
        ),
        Kind.LSP: KindSpec(
            label='LSP server',
            builder=None,
            directory=None,
            files=('.lsp.json',),
            opener=(
                'Add the `{name}` language server entry to .lsp.json of the plugin at {root}: '
                '{purpose}'
            ),
            reference='references/lsp.md',
        ),
        Kind.EXECUTABLE: KindSpec(
            label='executable',
            builder=None,
            directory='bin',
            files=('bin/{name}',),
            opener=('Write the `{name}` executable in bin/ of the plugin at {root}: {purpose}'),
            reference=None,
        ),
        Kind.OUTPUT_STYLE: KindSpec(
            label='output style',
            builder=None,
            directory='output-styles',
            files=('output-styles/{name}.md',),
            opener=(
                'Write the `{name}` output style in output-styles/ of the plugin at {root}: '
                '{purpose}'
            ),
            reference=None,
        ),
    }


def outside_plugin_kinds() -> dict[str, str]:
    return {
        OutsideKind.RULE: (
            'a plugin cannot ship rules; record the guidance as an outside_plugin entry whose '
            'mechanism is a project rule file .claude/rules/<name>.md or CLAUDE.md'
        ),
        OutsideKind.EXTENSION: (
            'Claude Code has no extensions directory in a plugin; record the need as an '
            'outside_plugin entry, or use a hook, an MCP server or an executable'
        ),
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class Kinds:
    specs: dict[str, KindSpec] = field(default_factory=kind_specs)
    outside: dict[str, str] = field(default_factory=outside_plugin_kinds)


RENAMED_KIND = 'worker'
RENAMED_TO = 'agent'
