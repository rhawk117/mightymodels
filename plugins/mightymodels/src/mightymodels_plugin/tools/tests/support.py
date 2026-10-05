import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent, Tool

from mightymodels_plugin.server import build_server

type ToolCall = tuple[str, dict[str, object]]


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
def state_server(repository: Path) -> StateServer:
    return StateServer(root=repository)


@pytest.fixture
def connected_server(state_server: StateServer) -> StateServer:
    state_server.connect()
    return state_server
