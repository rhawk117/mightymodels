import time
from typing import TYPE_CHECKING

import anyio
import pytest
from mightymodels_mcp.review_metrics.use_cases import METRICS_FILE

from tests.mcp.review.review_harness import create_review_harness
from tests.mcp.server.server_harness import view_of
from tests.mcp.ticket.ticket_harness import SLUG

if TYPE_CHECKING:
    from pathlib import Path

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


class SlowMeasure:
    def measure(self, root: Path) -> list[object]:
        assert root
        time.sleep(SLOW_SECONDS)
        return []


class Ticker:
    def __init__(self) -> None:
        self.ticks = 0

    async def run(self, done: anyio.Event) -> None:
        while not done.is_set():
            await anyio.sleep(TICK_SECONDS)
            self.ticks += 1


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

    async def test_options_cut_the_summary(self, harness: ReviewHarness) -> None:
        write_source(harness.server.repository)
        started = await harness.start()
        arguments = {'run_id': started.run_id, 'package_depth': 2, 'max_listed': 1}

        view_of(await harness.call('review_metrics', arguments))

        assert harness.server.repository.joinpath(started.directory, METRICS_FILE).is_file()

    async def test_zero_max_listed_is_refused(self, harness: ReviewHarness) -> None:
        started = await harness.start()

        result = await harness.call('review_metrics', {'run_id': started.run_id, 'max_listed': 0})

        assert result.is_error

    async def test_loop_stays_responsive_during_a_measurement(
        self, harness: ReviewHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started = await harness.start()
        monkeypatch.setattr(
            'mightymodels_mcp.review_metrics.use_cases.collect_metrics', SlowMeasure().measure
        )
        ticker = Ticker()
        done = anyio.Event()

        async with anyio.create_task_group() as group:
            group.start_soon(ticker.run, done)
            view_of(await harness.call('review_metrics', {'run_id': started.run_id}))
            done.set()

        assert ticker.ticks >= MIN_TICKS
