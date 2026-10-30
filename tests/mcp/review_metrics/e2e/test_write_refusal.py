"""A run directory that cannot take the metrics file is one tool error without a trace."""

from typing import TYPE_CHECKING

from mightymodels_mcp.review_metrics.use_cases import METRICS_FILE

from tests.mcp.review.review_harness import create_review_harness

if TYPE_CHECKING:
    from tests.mcp.server.server_harness import ServerHarness


class TestWriteRefusal:
    async def test_unwritable_run_directory_is_one_tool_error(
        self, server_harness: ServerHarness
    ) -> None:
        harness = await create_review_harness(server_harness)
        started = await harness.start()
        server_harness.repository.joinpath(started.directory, METRICS_FILE).mkdir(parents=True)

        result = await harness.call('review_metrics', {'run_id': started.run_id})

        text = str(result.content)
        assert result.is_error
        assert 'could not write' in text
        assert 'Traceback' not in text
