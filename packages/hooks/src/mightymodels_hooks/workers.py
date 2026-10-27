"""The plugin's workers and the agent type each one is dispatched under.

The roster and each worker's folder come from core's routing table. A worker's type is
`mightymodels:<folder>:<name>`, the folder being the one its agent file is in. A target is a worker
under its type or under its bare name.
"""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import create_routing_table

if TYPE_CHECKING:
    from mightymodels_core.primitives import AgentName

PLUGIN_PREFIX = 'mightymodels:'


def agent_type(name: AgentName) -> str:
    return f'{PLUGIN_PREFIX}{create_routing_table().folders[name]}:{name}'


def worker_named(name: str) -> AgentName | None:
    folders = create_routing_table().folders
    return next((worker for worker in folders if name in {worker, agent_type(worker)}), None)


def plugin_caller(agent_type: str | None) -> str | None:
    return agent_type if agent_type is not None and agent_type.startswith(PLUGIN_PREFIX) else None
