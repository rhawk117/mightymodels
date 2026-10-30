import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from mcp import Client
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.review_signals.history import without_deleted_files
from mightymodels_mcp.review_signals.reports import code_hotspots
from mightymodels_mcp.server.app import create_server

from tests.core.git.git_builders import run_git
from tests.mcp.server.server_harness import view_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from _pytest.mark import ParameterSet
    from mcp.types import CallToolResult

    from tests.mcp.server.server_harness import ServerHarness

TOOLS = ('signals_code_churn', 'signals_change_coupling', 'signals_code_hotspots')
RESULT_LIMIT = 50_000
DEFAULT_LIMIT = 25
CAPPED = 3
FILE_COUNT = 30
COUPLED_FILES = 8
COUPLED_COMMITS = 3
SLOW_SECONDS = 0.4
TICK_SECONDS = 0.02
MIN_TICKS = 5


async def call(server: ServerHarness, name: str, arguments: dict[str, Any]) -> CallToolResult:
    catalog = create_catalog()
    async with Client(create_server(server.dependencies, catalog)) as client:
        return await client.call_tool(name, arguments)


async def commit(server: ServerHarness, names: list[str]) -> None:
    for name in names:
        path = server.repository.joinpath(name)
        path.write_text(f'def {path.stem}():\n    return 1\n', encoding='utf-8')
        await run_git(server.repository, 'add', name)
    await run_git(server.repository, 'commit', '-q', '-m', 'change')


@pytest.fixture
def ticker() -> Ticker:
    return Ticker()


@pytest.fixture
async def history(server_harness: ServerHarness) -> ServerHarness:
    for index in range(FILE_COUNT):
        await commit(server_harness, [f'file_{index:02}.py'])

    coupled = [f'coupled_{index}.py' for index in range(COUPLED_FILES)]
    for round_number in range(COUPLED_COMMITS):
        for name in coupled:
            path = server_harness.repository.joinpath(name)
            path.write_text(f'VALUE = {round_number}\n', encoding='utf-8')
        await run_git(server_harness.repository, 'add', '.')
        await run_git(server_harness.repository, 'commit', '-q', '-m', 'together')
    return server_harness


class Ticker:
    def __init__(self) -> None:
        self.ticks = 0

    async def run(self, done: anyio.Event) -> None:
        while not done.is_set():
            await anyio.sleep(TICK_SECONDS)
            self.ticks += 1


@dataclass(slots=True, kw_only=True)
class SlowStandIn:
    ticker: Ticker
    real: Callable[..., Any]
    ticks_before: int | None = None
    ticks_after: int | None = None

    @property
    def ticks_inside(self) -> int:
        assert self.ticks_before is not None
        assert self.ticks_after is not None
        return self.ticks_after - self.ticks_before

    def call(self, *arguments: Any) -> Any:
        if self.ticks_before is None:
            self.ticks_before = self.ticker.ticks
            time.sleep(SLOW_SECONDS)
            self.ticks_after = self.ticker.ticks
        return self.real(*arguments)


@dataclass(slots=True, kw_only=True, frozen=True)
class SlowTarget:
    name: str
    path: str
    real: Callable[..., Any]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def slow_stand_in_cases() -> pytest.MarkDecorator:
    report = SlowTarget(
        name='report',
        path='mightymodels_mcp.review_signals.tools.code_hotspots',
        real=code_hotspots,
    )
    parsing = SlowTarget(
        name='parsing',
        path='mightymodels_mcp.review_signals.history.without_deleted_files',
        real=without_deleted_files,
    )
    return pytest.mark.parametrize('target', [report.param, parsing.param])


def signals_of(result: CallToolResult) -> list[dict[str, Any]]:
    return view_of(result)['signals']


class TestSignalsTools:
    @pytest.mark.parametrize('name', TOOLS)
    async def test_default_result_is_structured_and_small(
        self, history: ServerHarness, name: str
    ) -> None:
        result = await call(history, name, {})

        signals = signals_of(result)
        assert len(json.dumps(view_of(result))) < RESULT_LIMIT
        assert len(signals) == DEFAULT_LIMIT

    @pytest.mark.parametrize('name', TOOLS)
    async def test_limit_caps_the_signals(self, history: ServerHarness, name: str) -> None:
        result = await call(history, name, {'limit': CAPPED})

        assert len(signals_of(result)) == CAPPED

    @pytest.mark.parametrize('name', TOOLS)
    async def test_target_starting_with_a_dash_reaches_git_after_the_separator(
        self, history: ServerHarness, name: str
    ) -> None:
        result = await call(history, name, {'target': '--output=pwned'})

        assert signals_of(result) == []
        assert not history.repository.joinpath('pwned').exists()

    @pytest.mark.parametrize('name', TOOLS)
    async def test_baseline_ref_starting_with_a_dash_is_refused(
        self, history: ServerHarness, name: str
    ) -> None:
        result = await call(history, name, {'baseline_ref': '--output=pwned'})

        assert result.is_error
        assert not history.repository.joinpath('pwned').exists()

    @pytest.mark.parametrize('name', TOOLS)
    async def test_target_outside_the_repository_is_a_tool_error(
        self, history: ServerHarness, name: str
    ) -> None:
        result = await call(history, name, {'target': '../elsewhere'})

        assert result.is_error
        assert 'outside the repository' in str(result.content)

    @pytest.mark.parametrize('name', TOOLS)
    async def test_zero_limit_is_refused(self, history: ServerHarness, name: str) -> None:
        result = await call(history, name, {'limit': 0})

        assert result.is_error

    async def test_coupling_takes_its_own_fields_and_churn_refuses_them(
        self, history: ServerHarness
    ) -> None:
        coupled = await call(history, 'signals_change_coupling', {'min_shared': COUPLED_COMMITS})
        refused = await call(history, 'signals_code_churn', {'min_shared': COUPLED_COMMITS})

        assert signals_of(coupled)
        assert refused.is_error

    @slow_stand_in_cases()
    async def test_loop_stays_responsive_during_a_report(
        self,
        history: ServerHarness,
        monkeypatch: pytest.MonkeyPatch,
        ticker: Ticker,
        target: SlowTarget,
    ) -> None:
        stand_in = SlowStandIn(ticker=ticker, real=target.real)
        monkeypatch.setattr(target.path, stand_in.call)
        done = anyio.Event()
        results: list[CallToolResult] = []

        async with anyio.create_task_group() as group:
            group.start_soon(ticker.run, done)
            results.append(await call(history, 'signals_code_hotspots', {}))
            done.set()

        assert not results[0].is_error
        assert stand_in.ticks_inside >= MIN_TICKS
