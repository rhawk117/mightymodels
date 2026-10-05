import asyncio
from collections.abc import Generator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum, auto
from pathlib import Path

import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent, Tool
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session, SessionTransaction

from mightymodels_plugin.database import Database, open_database
from mightymodels_plugin.server import build_server
from mightymodels_plugin.workspace import Workspace, workspace_at

type ToolCall = tuple[str, dict[str, object]]


class ActivityKind(StrEnum):
    TRANSACTION_OPENED = auto()
    ENGINE_DISPOSED = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseEvent:
    kind: ActivityKind
    engine: Engine


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabaseActivity:
    events: list[DatabaseEvent] = field(default_factory=list)

    def record_transaction(self, session: Session, transaction: SessionTransaction) -> None:
        if transaction.parent is not None:
            return
        engine = session.get_bind().engine
        self.events.append(DatabaseEvent(kind=ActivityKind.TRANSACTION_OPENED, engine=engine))

    def record_disposal(self, engine: Engine) -> None:
        self.events.append(DatabaseEvent(kind=ActivityKind.ENGINE_DISPOSED, engine=engine))

    def kinds(self) -> list[ActivityKind]:
        return [recorded.kind for recorded in self.events]

    def engines(self) -> set[Engine]:
        return {recorded.engine for recorded in self.events}


def tree(top: Path) -> dict[str, bytes]:
    files = (path for path in sorted(top.rglob('*')) if path.is_file())
    return {str(path.relative_to(top)): path.read_bytes() for path in files}


def text_of(result: CallToolResult) -> str:
    return ''.join(block.text for block in result.content if isinstance(block, TextContent))


async def served_name(root: Path) -> str | None:
    async with Client(build_server(root)) as client:
        return client.server_info.name if client.server_info else None


async def served_tools(root: Path) -> dict[str, Tool]:
    async with Client(build_server(root)) as client:
        listed = await client.list_tools()
    return {tool.name: tool for tool in listed.tools}


async def call_results(root: Path, calls: Sequence[ToolCall]) -> list[CallToolResult]:
    async with Client(build_server(root)) as client:
        return [await client.call_tool(name, arguments) for name, arguments in calls]


@dataclass(slots=True, kw_only=True, frozen=True)
class StateServer:
    root: Path

    def name(self) -> str | None:
        return asyncio.run(served_name(self.root))

    def tools(self) -> dict[str, Tool]:
        return asyncio.run(served_tools(self.root))

    def call(self, *calls: ToolCall) -> list[CallToolResult]:
        return asyncio.run(call_results(self.root, calls))

    def connect(self) -> None:
        self.call()


@pytest.fixture
def repository_workspace(repository: Path) -> Workspace:
    workspace = workspace_at(repository)
    workspace.exclude_state_from_git()
    return workspace


@pytest.fixture
def repository_database(repository_workspace: Workspace) -> Generator[Database]:
    with open_database(repository_workspace.database_file()) as database:
        yield database


@pytest.fixture
def state_server(repository: Path) -> StateServer:
    return StateServer(root=repository)


@pytest.fixture
def connected_server(state_server: StateServer) -> StateServer:
    state_server.connect()
    return state_server


@pytest.fixture
def tree_after_the_connect(connected_server: StateServer) -> dict[str, bytes]:
    return tree(connected_server.root)


@pytest.fixture
def database_activity() -> Generator[DatabaseActivity]:
    activity = DatabaseActivity()
    event.listen(Session, 'after_transaction_create', activity.record_transaction)
    event.listen(Engine, 'engine_disposed', activity.record_disposal)
    yield activity
    event.remove(Session, 'after_transaction_create', activity.record_transaction)
    event.remove(Engine, 'engine_disposed', activity.record_disposal)
