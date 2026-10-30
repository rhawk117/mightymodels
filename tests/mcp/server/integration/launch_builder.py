import os
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.client.stdio import StdioServerParameters
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from tests.mcp.server.server_harness import ServerHarness

CHECKOUT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT_VARIABLE = '${CLAUDE_PLUGIN_ROOT}'
ENVIRONMENT_VARIABLE = 'UV_PROJECT_ENVIRONMENT'
CACHE_VARIABLE = 'UV_CACHE_DIR'
SERVER_NAME = 'workflow_state'


class DeclaredServer(BaseModel):
    command: str
    args: list[str]
    env: dict[str, str]


class PluginMcpConfig(BaseModel):
    servers: dict[str, DeclaredServer] = Field(alias='mcpServers')


def expand(value: str) -> str:
    return value.replace(PLUGIN_ROOT_VARIABLE, str(CHECKOUT))


def load_declared_servers() -> dict[str, DeclaredServer]:
    return PluginMcpConfig.model_validate_json(
        CHECKOUT.joinpath('mcp-servers', 'workflow_state.json').read_text()
    ).servers


def create_launch_parameters(
    *, declared: DeclaredServer, server_harness: ServerHarness, environment_directory: Path
) -> StdioServerParameters:
    inherited = {
        name: os.environ[name] for name in ('PATH', 'HOME', CACHE_VARIABLE) if name in os.environ
    }
    environ = {
        **inherited,
        **{name: expand(value) for name, value in declared.env.items()},
        **server_harness.environ,
        ENVIRONMENT_VARIABLE: str(environment_directory),
    }
    return StdioServerParameters(
        command=declared.command,
        args=[expand(argument) for argument in declared.args],
        env=environ,
        cwd=server_harness.repository,
    )
