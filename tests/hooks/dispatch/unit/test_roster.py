import pytest
from mightymodels_core.primitives import create_routing_table
from mightymodels_hooks.workers import agent_type, worker_named

pytestmark = pytest.mark.unit

ROUTING = create_routing_table()


class TestRoster:
    def test_every_routed_agent_resolves_from_its_agent_type(self) -> None:
        resolved = {worker_named(agent_type(name)) for name in ROUTING.folders}

        assert resolved == set(ROUTING.folders)

    def test_agent_type_names_the_folder_of_the_routing_table(self) -> None:
        assert agent_type('engineer') == 'mightymodels:workers:engineer'
