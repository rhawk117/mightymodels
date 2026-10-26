"""The real server over real dependencies: core's `open_state`, sqlite and a tmp git repository."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import anyio
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.state import LocalStateOpener

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.server.mcpserver import MCPServer
    from mcp.types import CallToolResult
    from mightymodels_mcp.server.registration import ToolCatalog


@dataclass(slots=True, kw_only=True, frozen=True)
class ServerHarness:
    data_directory: Path
    repository: Path

    @property
    def environ(self) -> dict[str, str]:
        return {PLUGIN_DATA_VARIABLE: str(self.data_directory)}

    @property
    def dependencies(self) -> ServerDependencies:
        state = LocalStateOpener(data_directory=self.data_directory, start=self.repository)
        return ServerDependencies(state=state)

    def create_server(self, catalog: ToolCatalog) -> MCPServer[ServerDependencies]:
        return create_server(self.dependencies, catalog)


def create_server_harness(root: Path) -> ServerHarness:
    repository = root.joinpath('repository').resolve()
    repository.mkdir()
    anyio.run(anyio.run_process, ['git', 'init', '--quiet', str(repository)])
    return ServerHarness(data_directory=root.joinpath('data', 'plugin'), repository=repository)


def view_of(result: CallToolResult) -> dict[str, Any]:
    assert not result.is_error, result.content
    assert result.structured_content
    return result.structured_content
