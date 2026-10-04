from dataclasses import dataclass

from vibe_code_cli.plugin.layout import planned
from vibe_code_cli.plugin.record import Component, Plan


@dataclass(slots=True, kw_only=True, frozen=True)
class Phase:
    number: int
    title: str
    purpose: str
    kinds: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class Context:
    plan: Plan
    root: str
    sessions: dict[str, str]


PHASES = (
    Phase(
        number=1,
        title='Foundation',
        purpose='What every later session assumes exists: the manifest and layout (written by '
        'render), then the hooks and output styles that shape every session.',
        kinds=('hook', 'output-style'),
    ),
    Phase(
        number=2,
        title='Capabilities',
        purpose='Servers and executables the agent can call. Built before the skills that teach '
        'when to call them, so those skills can name real tools.',
        kinds=('mcp', 'lsp', 'executable'),
    ),
    Phase(
        number=3,
        title='Skills and delegation',
        purpose='Procedures and entry points, then the agents they delegate to. Agents last '
        'because their discovery after install is the thing to verify.',
        kinds=('skill', 'command', 'agent'),
    ),
    Phase(
        number=4,
        title='Verify and distribute',
        purpose='Install the plugin the way its users will, check every component is discovered, '
        'then publish through the chosen channel.',
        kinds=(),
    ),
)


def phase_components(plan: Plan, phase: Phase) -> list[Component]:
    return [c for kind in phase.kinds for c in planned(plan) if c.kind == kind]


def session_ids(plan: Plan) -> dict[str, str]:
    ids: dict[str, str] = {}
    for phase in PHASES:
        for index, component in enumerate(phase_components(plan, phase), start=1):
            ids[component.name] = f'{phase.number}.{index}'
    return ids
