"""Build the workflow_state MCP server over an injected dependencies container."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcp.server.mcpserver import MCPServer
from mcp.server.request_state import RequestStateSecurity

from .icons import load_icon

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from .dependencies import ServerDependencies
    from .registration import ToolCatalog

SERVER_NAME = 'workflow_state'
REQUEST_STATE_TTL_SECONDS = 3600
INSTRUCTIONS = (
    'Tools read and change the mightymodels workflow state of the current repository. '
    'When a call fails with "Invalid or expired requestState", call the same tool again '
    'without requestState to start the exchange over.'
)


@dataclass(slots=True, kw_only=True, frozen=True)
class DependenciesLifespan:
    dependencies: ServerDependencies

    @asynccontextmanager
    async def open(self, _: MCPServer[ServerDependencies]) -> AsyncGenerator[ServerDependencies]:
        yield self.dependencies


def create_request_state_security() -> RequestStateSecurity:
    return RequestStateSecurity.ephemeral(ttl=REQUEST_STATE_TTL_SECONDS)


def create_server(
    dependencies: ServerDependencies, catalog: ToolCatalog
) -> MCPServer[ServerDependencies]:
    lifespan = DependenciesLifespan(dependencies=dependencies)
    return MCPServer(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        icons=[load_icon('server')],
        tools=catalog.list_tools(),
        lifespan=lifespan.open,
        request_state_security=create_request_state_security(),
    )
