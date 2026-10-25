from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.edge import DataDirectoryMissingError
from mightymodels_mcp.server.app import (
    DependenciesLifespan,
    create_request_state_security,
    create_server,
)
from mightymodels_mcp.server.dependencies import ServerDependencies, StateOpener
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolCatalog

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from mcp.server.mcpserver import MCPServer
    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import StateError


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedState:
    refusal: StateError

    async def __aenter__(self) -> OpenState:
        raise self.refusal

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusingStateOpener:
    refusal: StateError

    def open(self) -> AbstractAsyncContextManager[OpenState]:
        return RefusedState(refusal=self.refusal)


class TestCreateServer:
    refusal = DataDirectoryMissingError(
        variable='CLAUDE_PLUGIN_DATA', session_variable='MIGHTYMODELS_DATA'
    )

    @pytest.fixture
    def dependencies(self) -> ServerDependencies:
        return ServerDependencies(state=RefusingStateOpener(refusal=self.refusal))

    @pytest.fixture
    def server(self, dependencies: ServerDependencies) -> MCPServer[ServerDependencies]:
        return create_server(dependencies, ToolCatalog())

    def test_name_is_workflow_state(self, server: MCPServer[ServerDependencies]) -> None:
        assert server.name == 'workflow_state'

    def test_icon_is_the_server_icon(self, server: MCPServer[ServerDependencies]) -> None:
        assert server.icons == [load_icon('server')]

    def test_instructions_say_to_retry_without_request_state(
        self, server: MCPServer[ServerDependencies]
    ) -> None:
        instructions = server.instructions or ''
        assert '"Invalid or expired requestState"' in instructions
        assert 'call the same tool again without requestState' in instructions

    def test_request_state_lives_an_hour(self) -> None:
        assert create_request_state_security().ttl == 3600

    def test_fake_opener_meets_the_seam(self, dependencies: ServerDependencies) -> None:
        assert isinstance(dependencies.state, StateOpener)

    async def test_lifespan_yields_the_container(
        self, dependencies: ServerDependencies, server: MCPServer[ServerDependencies]
    ) -> None:
        lifespan = DependenciesLifespan(dependencies=dependencies)
        async with lifespan.open(server) as yielded:
            assert yielded is dependencies
