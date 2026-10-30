"""The review_metrics tool: measure the project root and write the report to the run's directory.

The measuring and the file write run in a worker thread after the run is read, so the event loop
stays free and no unit is held across the await.
"""

from typing import TYPE_CHECKING

from anyio import to_thread
from mightymodels_core.workspace import workspace_at

from mightymodels_mcp.review.views import ReviewView
from mightymodels_mcp.server.annotations import WRITES
from mightymodels_mcp.server.registration import ToolSpec, open_tool_state, register_specs

from .schemas import ReviewMetricsRequest
from .use_cases import create_metrics_work, locate_metrics, write_metrics

if TYPE_CHECKING:
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext


async def review_metrics(request: ReviewMetricsRequest, ctx: ToolContext) -> ReviewView:
    """Measure the repository and write uncle-bob-metrics.json to a review run's directory."""
    async with open_tool_state(ctx) as state:
        workspace = workspace_at(state.checkout.toplevel)
        target = locate_metrics(create_metrics_work(state), workspace, request)

    text = await to_thread.run_sync(write_metrics, target)
    return ReviewView(text=text, run_id=request.run_id)


REVIEW_METRICS_TOOLS = (
    ToolSpec(
        name='review_metrics',
        title='Measure the code for a review',
        annotations=WRITES,
        icon='review',
        request_model=ReviewMetricsRequest,
        result_model=ReviewView,
        handler=review_metrics,
    ),
)


def register_review_metrics_tools(catalog: ToolCatalog) -> ToolCatalog:
    return register_specs(catalog, REVIEW_METRICS_TOOLS)
