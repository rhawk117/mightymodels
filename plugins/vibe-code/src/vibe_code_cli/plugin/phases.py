from dataclasses import dataclass

from vibe_code_cli.plugin.layout import planned
from vibe_code_cli.plugin.record import Component, Plan


@dataclass(frozen=True)
class Phase:
    number: int
    title: str
    purpose: str
    kinds: tuple[str, ...]


@dataclass(frozen=True)
class Context:
    """What the text writers share: the plan, where the plugin root is, and each session number."""

    plan: Plan
    root: str
    sessions: dict[str, str]


# An executable sits ahead of the skills that call it, and agents come last (PP-A48).
PHASES = (
    Phase(
        1,
        'Foundation',
        'What every later session assumes exists: the manifest and layout (written by '
        'render), then the hooks and output styles that shape every session.',
        ('hook', 'output-style'),
    ),
    Phase(
        2,
        'Capabilities',
        'Servers and executables the agent can call. Built before the skills that teach when '
        'to call them, so those skills can name real tools.',
        ('mcp', 'lsp', 'executable'),
    ),
    Phase(
        3,
        'Skills and delegation',
        'Procedures and entry points, then the agents they delegate to. Agents last because '
        'their discovery after install is the thing to verify.',
        ('skill', 'command', 'agent'),
    ),
    Phase(
        4,
        'Verify and distribute',
        'Install the plugin the way its users will, check every component is discovered, '
        'then publish through the chosen channel.',
        (),
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
