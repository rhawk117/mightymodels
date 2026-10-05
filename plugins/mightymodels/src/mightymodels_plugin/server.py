"""The `state` MCP server the plugin registers in `.mcp.json`: its lifespan state and its tools.

The lifespan builds one workspace, opens the database once and builds each service over what it
needs of the two when a client connects, and disposes the engine when the client closes. Git is
optional: inside a repository the state directory is excluded from it, and outside one, or with
no git binary, the server starts all the same.

`AppState` holds one service per tool and nothing else: the workspace and the database are
reached only through the services built over them.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server import MCPServer

from mightymodels_plugin.database import open_database
from mightymodels_plugin.tools.close.service import CloseService
from mightymodels_plugin.tools.close.tool import close_tool
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.contract.tool import contract_tool
from mightymodels_plugin.tools.crashout.service import CrashoutService
from mightymodels_plugin.tools.crashout.tool import crashout_tool
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.investigation.tool import investigation_tool
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.review.tool import review_tool
from mightymodels_plugin.tools.snapshot.service import SnapshotService
from mightymodels_plugin.tools.snapshot.tool import snapshot_tool
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.task.tool import task_tool
from mightymodels_plugin.tools.ticket.service import TicketService
from mightymodels_plugin.tools.ticket.tool import ticket_tool
from mightymodels_plugin.workspace import find_root, workspace_at

SERVER_NAME = 'state'
TOOLS = (
    ticket_tool.ticket,
    task_tool.task,
    contract_tool.contract,
    review_tool.review,
    snapshot_tool.snapshot,
    close_tool.close,
    investigation_tool.investigation,
    crashout_tool.crashout,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class AppState:
    tickets: TicketService
    tasks: TaskService
    contracts: ContractService
    reviews: ReviewService
    snapshots: SnapshotService
    closings: CloseService
    investigations: InvestigationService
    crashouts: CrashoutService


def build_server(root: Path) -> MCPServer[AppState]:
    @asynccontextmanager
    async def lifespan(_: MCPServer[AppState]) -> AsyncGenerator[AppState]:
        workspace = workspace_at(root)
        workspace.exclude_state_from_git()
        with open_database(workspace.database_file()) as database:
            yield AppState(
                tickets=TicketService(workspace=workspace, database=database),
                tasks=TaskService(workspace=workspace, database=database),
                contracts=ContractService(workspace=workspace, database=database),
                reviews=ReviewService(workspace=workspace, database=database),
                snapshots=SnapshotService(workspace=workspace, database=database),
                closings=CloseService(workspace=workspace, database=database),
                investigations=InvestigationService(workspace=workspace, database=database),
                crashouts=CrashoutService(database=database),
            )

    server = MCPServer(SERVER_NAME, lifespan=lifespan)
    for tool in TOOLS:
        server.add_tool(tool)
    return server


def serve() -> None:
    build_server(find_root(os.environ, Path.cwd())).run()
