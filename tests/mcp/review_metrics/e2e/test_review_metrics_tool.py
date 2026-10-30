import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
import pytest
from mightymodels_mcp.review_metrics.use_cases import METRICS_FILE

from tests.mcp.review.review_harness import create_review_harness
from tests.mcp.server.server_harness import view_of
from tests.mcp.ticket.ticket_harness import SLUG

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.types import CallToolResult

    from tests.mcp.review.review_harness import ReviewHarness
    from tests.mcp.server.server_harness import ServerHarness

UNKNOWN_RUN = '20200101-000000'
SLOW_SECONDS = 0.4
TICK_SECONDS = 0.02
MIN_TICKS = 5


@pytest.fixture
async def harness(server_harness: ServerHarness) -> ReviewHarness:
    return await create_review_harness(server_harness)


def write_source(repository: Path) -> None:
    repository.joinpath('pkg').mkdir()
    repository.joinpath('pkg', 'mod.py').write_text('def one():\n    return 1\n', encoding='utf-8')


def write_two_violations(repository: Path) -> None:
    for package in ('alpha', 'beta'):
        directory = repository.joinpath('pkg', package)
        directory.mkdir(parents=True)
        directory.joinpath('mod.py').write_text(
            'def many(a, b, c, d):\n    return a, b, c, d\n', encoding='utf-8'
        )


class Ticker:
    def __init__(self) -> None:
        self.ticks = 0

    async def run(self, done: anyio.Event) -> None:
        while not done.is_set():
            await anyio.sleep(TICK_SECONDS)
            self.ticks += 1


@dataclass(slots=True, kw_only=True)
class SlowMeasure:
    ticker: Ticker
    ticks_before: int | None = None
    ticks_after: int | None = None

    @property
    def ticks_inside(self) -> int:
        assert self.ticks_before is not None
        assert self.ticks_after is not None
        return self.ticks_after - self.ticks_before

    def measure(self, root: Path) -> list[object]:
        assert root
        self.ticks_before = self.ticker.ticks
        time.sleep(SLOW_SECONDS)
        self.ticks_after = self.ticker.ticks
        return []


class TestReviewMetrics:
    async def test_request_without_run_id_is_refused(self, harness: ReviewHarness) -> None:
        result = await harness.call('review_metrics', {})

        assert result.is_error

    async def test_unknown_run_is_refused_with_core_message(self, harness: ReviewHarness) -> None:
        result = await harness.call('review_metrics', {'run_id': UNKNOWN_RUN})

        assert result.is_error
        assert f'no review run {UNKNOWN_RUN}; start one first' in str(result.content)

    async def test_run_without_a_ticket_gets_the_file_and_the_path_in_the_text(
        self, harness: ReviewHarness
    ) -> None:
        write_source(harness.server.repository)
        started = await harness.start()

        view = view_of(await harness.call('review_metrics', {'run_id': started.run_id}))

        written = harness.server.repository.joinpath(started.directory, METRICS_FILE)
        assert written.is_file()
        assert f'wrote {started.directory}/{METRICS_FILE}' in view['text']
        assert 'files\t1' in view['text']

    async def test_run_with_a_ticket_gets_the_file_in_the_ticket_directory(
        self, harness: ReviewHarness
    ) -> None:
        write_source(harness.server.repository)
        started = await harness.start(scope='ticket', slug=SLUG, base='main')

        view = view_of(await harness.call('review_metrics', {'run_id': started.run_id}))

        written = harness.server.repository.joinpath(started.directory, METRICS_FILE)
        assert started.directory.startswith(f'.mightymodels/{SLUG}/review/')
        assert written.read_text(encoding='utf-8').startswith('{\n')
        assert f'wrote {started.directory}/{METRICS_FILE}' in view['text']

    async def test_options_cut_the_listed_violations_and_set_the_package_depth(
        self, harness: ReviewHarness
    ) -> None:
        write_two_violations(harness.server.repository)
        started = await harness.start()
        arguments = {'run_id': started.run_id, 'package_depth': 2, 'max_listed': 1}

        view_of(await harness.call('review_metrics', arguments))

        written = harness.server.repository.joinpath(started.directory, METRICS_FILE)
        report = json.loads(written.read_text(encoding='utf-8'))
        params = report['violations']['functions_over_3_params']
        assert params['count'] == 2
        assert len(params['worst']) == 1
        assert set(report['component_metrics']['packages']) == {'pkg.alpha', 'pkg.beta'}

    @pytest.mark.parametrize('option', ['max_listed', 'package_depth'])
    async def test_zero_option_is_refused(self, harness: ReviewHarness, option: str) -> None:
        started = await harness.start()

        result = await harness.call('review_metrics', {'run_id': started.run_id, option: 0})

        assert result.is_error

    async def test_loop_stays_responsive_during_a_measurement(
        self, harness: ReviewHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started = await harness.start()
        ticker = Ticker()
        slow = SlowMeasure(ticker=ticker)
        monkeypatch.setattr(
            'mightymodels_mcp.review_metrics.use_cases.collect_metrics', slow.measure
        )
        done = anyio.Event()
        results: list[CallToolResult] = []

        async with anyio.create_task_group() as group:
            group.start_soon(ticker.run, done)
            results.append(await harness.call('review_metrics', {'run_id': started.run_id}))
            done.set()

        assert not results[0].is_error
        assert slow.ticks_inside >= MIN_TICKS
