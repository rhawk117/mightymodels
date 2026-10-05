import asyncio

from mcp import Client
from mightymodels_plugin.server import SERVER_NAME, build_server


async def list_tool_names() -> list[str]:
    async with Client(build_server()) as client:
        result = await client.list_tools()
    return [tool.name for tool in result.tools]


async def read_server_name() -> str | None:
    async with Client(build_server()) as client:
        return client.server_info.name if client.server_info else None


class TestStateServer:
    def test_is_named_state(self) -> None:
        assert asyncio.run(read_server_name()) == SERVER_NAME == 'state'

    def test_lists_its_tools_through_the_in_memory_client(self) -> None:
        assert asyncio.run(list_tool_names()) == []
