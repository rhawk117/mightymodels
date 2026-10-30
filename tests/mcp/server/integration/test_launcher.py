import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mcp.client.client import Client
from mightymodels_mcp.main import create_catalog

from tests.mcp.server.integration.launch_builder import (
    CHECKOUT,
    create_launch_parameters,
    load_declared_servers,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.client.stdio import StdioServerParameters

    from tests.mcp.server.integration.launch_builder import (
        DeclaredServer,
    )
    from tests.mcp.server.server_harness import ServerHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class Launcher:
    servers: dict[str, DeclaredServer]
    parameters: StdioServerParameters


class TestLauncher:
    SERVER_NAME = 'workflow_state'

    @pytest.fixture
    def servers(self) -> dict[str, DeclaredServer]:
        return load_declared_servers()

    @pytest.fixture
    def launcher(
        self, servers: dict[str, DeclaredServer], server_harness: ServerHarness, tmp_path: Path
    ) -> Launcher:
        parameters = create_launch_parameters(
            declared=servers[self.SERVER_NAME],
            server_harness=server_harness,
            environment_directory=tmp_path.joinpath('venv'),
        )
        return Launcher(servers=servers, parameters=parameters)

    def test_declares_only_the_workflow_state_server(self, launcher: Launcher) -> None:
        assert list(launcher.servers) == [self.SERVER_NAME]

    async def test_declared_command_serves_every_tool_over_stdio(self, launcher: Launcher) -> None:
        async with Client(launcher.parameters) as client:
            listed = await client.list_tools()

        names = [tool.name for tool in listed.tools]
        assert len(names) == 36
        assert sorted(names) == sorted(create_catalog().tools)


class TestPluginOnlyServer:
    def test_plugin_only_server_file_is_the_one_plugin_json_names(self) -> None:
        manifest = json.loads(CHECKOUT.joinpath('.claude-plugin', 'plugin.json').read_text())

        assert manifest['mcpServers'] == './mcp-servers/workflow_state.json'

    def test_plugin_only_root_mcp_json_declares_no_servers(self) -> None:
        project_config = json.loads(CHECKOUT.joinpath('.mcp.json').read_text())

        assert project_config['mcpServers'] == {}
