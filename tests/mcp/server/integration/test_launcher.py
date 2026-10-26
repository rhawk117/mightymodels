import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters
from mightymodels_mcp.server.entrypoint import create_catalog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from tests.mcp.server.server_harness import ServerHarness

CHECKOUT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT_VARIABLE = '${CLAUDE_PLUGIN_ROOT}'
ENVIRONMENT_VARIABLE = 'UV_PROJECT_ENVIRONMENT'
CACHE_VARIABLE = 'UV_CACHE_DIR'


class DeclaredServer(BaseModel):
    command: str
    args: list[str]
    env: dict[str, str]


class PluginMcpConfig(BaseModel):
    servers: dict[str, DeclaredServer] = Field(alias='mcpServers')


@dataclass(slots=True, kw_only=True, frozen=True)
class Launcher:
    servers: dict[str, DeclaredServer]
    parameters: StdioServerParameters


def expand(value: str) -> str:
    return value.replace(PLUGIN_ROOT_VARIABLE, str(CHECKOUT))


class TestLauncher:
    SERVER_NAME = 'workflow_state'

    @pytest.fixture
    def servers(self) -> dict[str, DeclaredServer]:
        return PluginMcpConfig.model_validate_json(
            CHECKOUT.joinpath('mcp', 'workflow_state.json').read_text()
        ).servers

    @pytest.fixture
    def launcher(
        self, servers: dict[str, DeclaredServer], server_harness: ServerHarness, tmp_path: Path
    ) -> Launcher:
        declared = servers[self.SERVER_NAME]
        inherited = {
            name: os.environ[name]
            for name in ('PATH', 'HOME', CACHE_VARIABLE)
            if name in os.environ
        }
        environ = {
            **inherited,
            **{name: expand(value) for name, value in declared.env.items()},
            **server_harness.environ,
            ENVIRONMENT_VARIABLE: str(tmp_path.joinpath('venv')),
        }
        parameters = StdioServerParameters(
            command=declared.command,
            args=[expand(argument) for argument in declared.args],
            env=environ,
            cwd=server_harness.repository,
        )
        return Launcher(servers=servers, parameters=parameters)

    def test_declares_only_the_workflow_state_server(self, launcher: Launcher) -> None:
        assert list(launcher.servers) == [self.SERVER_NAME]

    async def test_declared_command_serves_every_tool_over_stdio(self, launcher: Launcher) -> None:
        async with Client(launcher.parameters) as client:
            listed = await client.list_tools()

        names = [tool.name for tool in listed.tools]
        assert len(names) == 32
        assert sorted(names) == sorted(create_catalog().tools)


class TestPluginOnlyServer:
    def test_plugin_only_server_file_is_the_one_plugin_json_names(self) -> None:
        manifest = json.loads(CHECKOUT.joinpath('.claude-plugin', 'plugin.json').read_text())

        assert manifest['mcpServers'] == './mcp/workflow_state.json'

    def test_plugin_only_root_mcp_json_declares_no_servers(self) -> None:
        project_config = json.loads(CHECKOUT.joinpath('.mcp.json').read_text())

        assert project_config['mcpServers'] == {}
