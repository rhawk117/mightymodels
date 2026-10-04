from dataclasses import dataclass

import msgspec
from msgspec import UNSET, UnsetType

from vibe_code_cli.mcp.file import McpFile

WRAPPER_KEY = 'mcpServers'


class McpServer(msgspec.Struct, rename='camel', frozen=True, kw_only=True):
    type: str | UnsetType = UNSET
    command: str | UnsetType = UNSET
    args: list[str] = []
    env: dict[str, str] = {}
    url: str | UnsetType = UNSET
    headers: dict[str, str] = {}
    headers_helper: str | UnsetType = UNSET
    oauth: dict[str, object] | UnsetType = UNSET
    timeout: int | UnsetType = UNSET
    always_load: bool | UnsetType = UNSET


class McpConfig(msgspec.Struct, rename='camel', frozen=True, kw_only=True):
    mcp_servers: dict[str, McpServer] = {}


class WrittenConfig(msgspec.Struct, rename='camel', frozen=True, kw_only=True):
    mcp_servers: dict[str, dict[str, object]] = {}


@dataclass(slots=True, kw_only=True, frozen=True)
class ServerEntry:
    server: McpServer
    keys: tuple[str, ...]


def server_entries(
    servers: dict[str, McpServer], written: dict[str, dict[str, object]]
) -> dict[str, ServerEntry]:
    return {
        name: ServerEntry(server=server, keys=tuple(written[name]))
        for name, server in servers.items()
    }


def decode_servers(mcp_file: McpFile) -> dict[str, ServerEntry]:
    document = mcp_file.document
    wrapped = mcp_file.kind == 'user' or (isinstance(document, dict) and WRAPPER_KEY in document)
    if wrapped:
        servers = msgspec.convert(document, McpConfig).mcp_servers
        written = msgspec.convert(document, WrittenConfig).mcp_servers
        return server_entries(servers, written)
    servers = msgspec.convert(document, dict[str, McpServer])
    written = msgspec.convert(document, dict[str, dict[str, object]])
    return server_entries(servers, written)
