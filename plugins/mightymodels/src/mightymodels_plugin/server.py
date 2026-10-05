"""The `state` MCP server the plugin registers in `.mcp.json`."""

from mcp.server.mcpserver import MCPServer

SERVER_NAME = 'state'


def build_server() -> MCPServer:
    return MCPServer(SERVER_NAME)


def serve() -> None:
    build_server().run()
