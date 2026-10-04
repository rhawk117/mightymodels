from dataclasses import dataclass

import msgspec
from msgspec import UNSET, UnsetType

from ai_engineer_cli.mcp.file import McpFile

WRAPPER_KEY = 'mcpServers'


class McpServer(msgspec.Struct, rename='camel'):
    """One server entry, typed as mcp.md shows its keys; `oauth` is read by no check."""

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


class McpConfig(msgspec.Struct, rename='camel'):
    """A config that holds its servers under `mcpServers`, beside keys no check reads."""

    mcp_servers: dict[str, McpServer] = {}


class WrittenConfig(msgspec.Struct, rename='camel'):
    """The same config with every server as written, so its keys can be listed."""

    mcp_servers: dict[str, dict[str, object]] = {}


@dataclass(frozen=True)
class ServerEntry:
    server: McpServer
    keys: tuple[str, ...]


def decode_servers(mcp_file: McpFile) -> dict[str, ServerEntry]:
    """The servers a file holds, each with the keys as written.

    Raises msgspec.ValidationError when the file has a value of the wrong type. A project or
    plugin file with no `mcpServers` key is a bare map of names to servers; a user file holds
    no servers without it.
    """
    document = mcp_file.document
    wrapped = mcp_file.kind == 'user' or (isinstance(document, dict) and WRAPPER_KEY in document)
    if wrapped:
        servers = msgspec.convert(document, McpConfig).mcp_servers
        written = msgspec.convert(document, WrittenConfig).mcp_servers
    else:
        servers = msgspec.convert(document, dict[str, McpServer])
        written = msgspec.convert(document, dict[str, dict[str, object]])
    return {name: ServerEntry(server, tuple(written[name])) for name, server in servers.items()}
