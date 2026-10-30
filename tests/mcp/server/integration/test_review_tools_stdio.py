import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters
from mightymodels_core.edge import DATABASE_NAME
from mightymodels_mcp.review_metrics.use_cases import METRICS_FILE
from pydantic import BaseModel, Field

from tests.core.git.git_builders import run_git
from tests.mcp.server.server_harness import view_of

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


@dataclass(slots=True, kw_only=True, frozen=True)
class Launched:
    parameters: StdioServerParameters
    server: ServerHarness


def expand(value: str) -> str:
    return value.replace(PLUGIN_ROOT_VARIABLE, str(CHECKOUT))


class TestReviewToolsOverStdio:
    TRACKED = ('alpha.py', 'beta.py')
    COMMITS = 3
    SCOPE = 'diff'
    DEPTH = 'standard'
    EMPHASIS = 'balanced'
    BASE = 'HEAD'

    @pytest.fixture
    async def launched(self, server_harness: ServerHarness, tmp_path: Path) -> Launched:
        for round_number in range(self.COMMITS):
            for name in self.TRACKED:
                server_harness.repository.joinpath(name).write_text(
                    f'VALUE = {round_number}\n', encoding='utf-8'
                )
            await run_git(server_harness.repository, 'add', '.')
            await run_git(server_harness.repository, 'commit', '-q', '-m', 'together')

        declared = PluginMcpConfig.model_validate_json(
            CHECKOUT.joinpath('mcp-servers', 'workflow_state.json').read_text()
        ).servers[SERVER_NAME]
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
        return Launched(parameters=parameters, server=server_harness)

    def start_arguments(self) -> dict[str, str]:
        return {
            'scope': self.SCOPE,
            'depth': self.DEPTH,
            'emphasis': self.EMPHASIS,
            'base': self.BASE,
        }

    async def test_review_tools_serve_the_temporary_repository_over_stdio(
        self, launched: Launched
    ) -> None:
        repository = launched.server.repository
        signals: dict[str, Any] = {}

        async with Client(launched.parameters) as client:
            started = view_of(await client.call_tool('review_start', self.start_arguments()))
            metrics = view_of(
                await client.call_tool('review_metrics', {'run_id': started['run_id']})
            )
            for name in ('signals_code_churn', 'signals_change_coupling', 'signals_code_hotspots'):
                signals[name] = view_of(await client.call_tool(name, {}))

        directory = f'.mightymodels/.runtime/reviews/{started["run_id"]}'
        written = repository.joinpath(directory, METRICS_FILE)
        assert f'wrote {directory}/{METRICS_FILE}' in metrics['text']
        assert written.is_file()
        assert not CHECKOUT.joinpath(directory).exists()
        for name, view in signals.items():
            text = json.dumps(view['signals'])
            assert all(file in text for file in self.TRACKED), name
        assert launched.server.data_directory.joinpath(DATABASE_NAME).is_file()
