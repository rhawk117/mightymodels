"""The `state` MCP server the plugin registers in `.mcp.json`: its lifespan state and its tools.

The lifespan builds one workspace, opens the database once and builds each service over the two
when a client connects, and disposes the engine when the client closes. Git is optional: inside a
repository the state directory is excluded from it, and outside one, or with no git binary, the
server starts all the same.

`AppState` holds a service per rebuilt tool. It keeps the workspace and the database for the
tools whose handlers still take a `Checkout`.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server import MCPServer

from mightymodels_plugin.database import Database, open_database
from mightymodels_plugin.tools.contract.tool import contract_tool
from mightymodels_plugin.tools.review.tool import review_tool
from mightymodels_plugin.tools.task.tool import task_tool
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tool import ticket_tool
from mightymodels_plugin.workspace import Workspace, find_root, workspace_at

SERVER_NAME = 'state'
TOOLS = (ticket_tool.ticket, task_tool.task, contract_tool.contract, review_tool.review)


@dataclass(slots=True, kw_only=True, frozen=True)
class AppState:
    workspace: Workspace
    database: Database
    tickets: TicketService


def build_server(root: Path) -> MCPServer[AppState]:
    @asynccontextmanager
    async def lifespan(_: MCPServer[AppState]) -> AsyncGenerator[AppState]:
        workspace = workspace_at(root)
        workspace.exclude_state_from_git()
        with open_database(workspace.database_file()) as database:
            yield AppState(
                workspace=workspace,
                database=database,
                tickets=TicketService(workspace=workspace, database=database),
            )

    server = MCPServer(SERVER_NAME, lifespan=lifespan)
    for tool in TOOLS:
        server.add_tool(tool)
    return server


def serve() -> None:
    build_server(find_root(os.environ, Path.cwd())).run()
