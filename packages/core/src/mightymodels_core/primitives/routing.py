"""Which model and effort each subagent runs on.

Every worker but the two reviewers has one fixed model at every scope. A reviewer's model comes
from the review's depth, and `override_model` is the one model a single review run may move its
heavier-weighted reviewer to. `folders` names the folder of `agents/` each worker's file is in.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from mightymodels_core.schemas.reviews import Depth

type Model = Literal['haiku', 'sonnet', 'opus', 'fable']


type Effort = Literal['low', 'medium', 'high', 'xhigh', 'max']


type ScopeSize = Literal['sm', 'med', 'large']


type AgentFolder = Literal['review', 'workers', 'triage']


type AgentName = Literal[
    'code-scout',
    'web-scout',
    'qualitylens',
    'fact-checker',
    'engineer',
    'architect',
    'intern',
    'gitty-up',
    'wingman',
    'terry-toolchain',
    'merge-vader',
    'uncle-bob',
]

REVIEWER_AGENTS: frozenset[AgentName] = frozenset({'merge-vader', 'uncle-bob'})


@dataclass(slots=True, kw_only=True, frozen=True)
class RoutingTable:
    folders: dict[AgentName, AgentFolder] = field(default_factory=dict)
    models: dict[AgentName, Model] = field(default_factory=dict)
    efforts: dict[Model, Effort] = field(default_factory=dict)
    depth_models: dict[Depth, Model] = field(default_factory=dict)
    override_model: Model = 'fable'
    default_scope: ScopeSize = 'med'

    def fixed_model(self, agent: AgentName) -> Model:
        return self.models[agent]

    def reviewer_model(self, depth: Depth) -> Model:
        return self.depth_models[depth]

    def effort_of(self, model: Model) -> Effort:
        return self.efforts[model]

    def assign(self, *, model: Model, agents: dict[AgentName, AgentFolder]) -> None:
        self.folders.update(agents)
        self.models.update(dict.fromkeys(agents, model))


def create_routing_table() -> RoutingTable:
    table = RoutingTable(
        efforts={'haiku': 'high', 'sonnet': 'medium', 'opus': 'medium', 'fable': 'high'},
        depth_models={'quick': 'sonnet', 'standard': 'opus', 'deep': 'opus'},
    )
    table.assign(
        model='haiku',
        agents={
            'code-scout': 'triage',
            'web-scout': 'triage',
            'qualitylens': 'review',
            'fact-checker': 'review',
            'intern': 'workers',
            'gitty-up': 'workers',
        },
    )
    table.assign(model='sonnet', agents={'engineer': 'workers', 'terry-toolchain': 'triage'})
    table.assign(
        model='opus',
        agents={'architect': 'workers', 'merge-vader': 'review', 'uncle-bob': 'review'},
    )
    table.assign(model='fable', agents={'wingman': 'triage'})
    return table
