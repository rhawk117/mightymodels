"""The `state` MCP server the plugin registers in `.mcp.json`."""

from mcp.server.mcpserver import MCPServer

from mightymodels_plugin.tools.contract import contract
from mightymodels_plugin.tools.review import review
from mightymodels_plugin.tools.task import task
from mightymodels_plugin.tools.ticket import ticket

SERVER_NAME = 'state'
TOOLS = (ticket, task, contract, review)


def build_server() -> MCPServer:
    server = MCPServer(SERVER_NAME)
    for tool in TOOLS:
        server.add_tool(tool)
    return server


def serve() -> None:
    build_server().run()
