"""The plugin's workers and the agent type each one is dispatched under.

The roster and each worker's folder come from core's routing table. A worker's type is
`mightymodels:<folder>:<name>`, the folder being the one its agent file is in. A target is a worker
under its type or under its bare name.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from mightymodels_core.primitives import create_routing_table

if TYPE_CHECKING:
    from mightymodels_core.primitives import AgentName

PLUGIN_PREFIX = 'mightymodels:'


@dataclass(slots=True, kw_only=True, frozen=True)
class PhaseSkills:
    skills: dict[str, str] = field(default_factory=dict)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.skills)

    def mount(self, phases: dict[str, str]) -> Self:
        self.skills.update(phases)
        return self


def create_phase_skills() -> PhaseSkills:
    return PhaseSkills().mount({
        'investigation': 'run mightymodels:lets-investigate, then mightymodels:open-ticket',
        'planning': (
            'run mightymodels:game-plan, or mightymodels:one-shot for a small ticket; '
            'stop before mightymodels:agents-assemble'
        ),
        'implementation': 'run mightymodels:agents-assemble, then mightymodels:stick-the-landing',
        'review': 'run mightymodels:review-circus',
    })


PHASE_AGENTS = create_phase_skills().names


def agent_type(name: AgentName) -> str:
    return f'{PLUGIN_PREFIX}{create_routing_table().folders[name]}:{name}'


def worker_named(name: str) -> AgentName | None:
    folders = create_routing_table().folders
    return next((worker for worker in folders if name in {worker, agent_type(worker)}), None)


def plugin_caller(agent_type: str | None) -> str | None:
    return agent_type if agent_type is not None and agent_type.startswith(PLUGIN_PREFIX) else None


def is_phase_agent(name: str) -> bool:
    return name.removeprefix(PLUGIN_PREFIX) in PHASE_AGENTS
