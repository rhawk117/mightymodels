"""The `state` MCP server the plugin registers in `.mcp.json`: its lifespan state and its tools.

The lifespan opens the database once when a client connects and disposes its engine when the
client closes. Git is optional: inside a repository the state directory is excluded from it, and
outside one the server starts all the same.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server import MCPServer

from mightymodels_plugin.database import open_database
from mightymodels_plugin.db.checkout import Checkouts
from mightymodels_plugin.db.repository import exclude_state_in_repository, find_root
from mightymodels_plugin.tools.contract.tool import contract_tool
from mightymodels_plugin.tools.review.tool import review_tool
from mightymodels_plugin.tools.task.tool import task_tool
from mightymodels_plugin.tools.ticket.tool import ticket_tool

SERVER_NAME = 'state'
TOOLS = (ticket_tool.ticket, task_tool.task, contract_tool.contract, review_tool.review)


@dataclass(slots=True, kw_only=True, frozen=True)
class AppState:
    checkouts: Checkouts


def build_server(root: Path) -> MCPServer[AppState]:
    @asynccontextmanager
    async def lifespan(_: MCPServer[AppState]) -> AsyncGenerator[AppState]:
        exclude_state_in_repository(root)
        with open_database(root) as database:
            yield AppState(checkouts=Checkouts(root=root, database=database))

    server = MCPServer(SERVER_NAME, lifespan=lifespan)
    for tool in TOOLS:
        server.add_tool(tool)
    return server


def serve() -> None:
    build_server(find_root(os.environ, Path.cwd())).run()
