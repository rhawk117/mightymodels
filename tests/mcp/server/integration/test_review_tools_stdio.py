import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from mcp.client.client import Client
from mightymodels_core.edge import DATABASE_NAME
from mightymodels_mcp.review_metrics.use_cases import METRICS_FILE

from tests.core.git.git_builders import run_git
from tests.mcp.server.integration.launch_builder import (
    CHECKOUT,
    SERVER_NAME,
    create_launch_parameters,
    load_declared_servers,
)
from tests.mcp.server.server_harness import view_of

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.client.stdio import StdioServerParameters

    from tests.mcp.server.server_harness import ServerHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class Launched:
    parameters: StdioServerParameters
    server: ServerHarness


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

        parameters = create_launch_parameters(
            declared=load_declared_servers()[SERVER_NAME],
            server_harness=server_harness,
            environment_directory=tmp_path.joinpath('venv'),
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
