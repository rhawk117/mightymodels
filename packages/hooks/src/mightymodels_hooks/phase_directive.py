"""The directive a phase agent's session starts with.

A phase launched with `claude --agent mightymodels:<phase>` carries no body of its own, so the
SessionStart hook hands it the skills it runs and the rule that ends it. The directive goes out on
a fresh session, a clear and a compaction, and stays silent on a resume or a fork, whose context
already holds it. It names no worker: the roster lives in the agent file's allowlist.
"""

import json

from mightymodels_hooks.workers import PHASE_AGENTS, PLUGIN_PREFIX

DIRECTIVE_SOURCES = frozenset({'startup', 'clear', 'compact'})
BOUNDARY_RULE = "End the phase with mightymodels:baton-pass; never invoke the next phase's skill."
PHASE_SKILLS = {
    'investigation': 'run mightymodels:lets-investigate, then mightymodels:open-ticket',
    'planning': (
        'run mightymodels:game-plan, or mightymodels:one-shot for a small ticket; '
        'stop before mightymodels:agents-assemble'
    ),
    'implementation': 'run mightymodels:agents-assemble, then mightymodels:stick-the-landing',
    'review': 'run mightymodels:review-circus',
}


def phase_of(agent_type: str | None) -> str | None:
    if agent_type is None or not agent_type.startswith(PLUGIN_PREFIX):
        return None

    phase = agent_type.removeprefix(PLUGIN_PREFIX)
    return phase if phase in PHASE_AGENTS else None


def directive_text(phase: str) -> str:
    return f'You are the mightymodels {phase} phase: {PHASE_SKILLS[phase]}. {BOUNDARY_RULE}'


def phase_directive(agent_type: str | None, source: str | None) -> str | None:
    phase = phase_of(agent_type)
    if phase is None or source not in DIRECTIVE_SOURCES:
        return None

    return json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'SessionStart',
            'additionalContext': directive_text(phase),
        }
    })
