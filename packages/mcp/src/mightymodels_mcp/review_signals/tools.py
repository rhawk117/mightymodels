"""The review signals tools: git history measurements, returned inline as structured results.

The state is opened only to read the checkout's root. Git runs through the async process runner,
and the report computation runs in a worker thread, so the event loop stays free.
"""

from typing import TYPE_CHECKING

from anyio import to_thread

from mightymodels_mcp.server.annotations import READS
from mightymodels_mcp.server.registration import ToolSpec, open_tool_state, register_specs

from .history import create_git_source, load_history
from .reports import (
    ChurnSignal,
    CouplingSignal,
    HotspotSignal,
    change_coupling,
    code_churn,
    code_hotspots,
)
from .schemas import ChangeCouplingRequest, CodeChurnRequest, CodeHotspotsRequest, Report
from .use_cases import options_of, root_of

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext


async def read_root(ctx: ToolContext) -> Path:
    async with open_tool_state(ctx) as state:
        return root_of(state)


async def signals_code_churn(request: CodeChurnRequest, ctx: ToolContext) -> Report[ChurnSignal]:
    """Rank the files in a git history window by commits and lines changed."""
    options = options_of(request)
    history = await load_history(options, create_git_source(await read_root(ctx)))
    return await to_thread.run_sync(code_churn, history, options)


async def signals_change_coupling(
    request: ChangeCouplingRequest, ctx: ToolContext
) -> Report[CouplingSignal]:
    """Rank the file pairs that change together in a git history window."""
    options = options_of(request)
    history = await load_history(options, create_git_source(await read_root(ctx)))
    return await to_thread.run_sync(change_coupling, history, options)


async def signals_code_hotspots(
    request: CodeHotspotsRequest, ctx: ToolContext
) -> Report[HotspotSignal]:
    """Rank the files that change often and are complex now."""
    options = options_of(request)
    history = await load_history(options, create_git_source(await read_root(ctx)))
    return await to_thread.run_sync(code_hotspots, history, options)


REVIEW_SIGNALS_TOOLS = (
    ToolSpec(
        name='signals_code_churn',
        title='Measure code churn',
        annotations=READS,
        icon='review',
        request_model=CodeChurnRequest,
        result_model=Report[ChurnSignal],
        handler=signals_code_churn,
    ),
    ToolSpec(
        name='signals_change_coupling',
        title='Measure change coupling',
        annotations=READS,
        icon='review',
        request_model=ChangeCouplingRequest,
        result_model=Report[CouplingSignal],
        handler=signals_change_coupling,
    ),
    ToolSpec(
        name='signals_code_hotspots',
        title='Measure code hotspots',
        annotations=READS,
        icon='review',
        request_model=CodeHotspotsRequest,
        result_model=Report[HotspotSignal],
        handler=signals_code_hotspots,
    ),
)


def register_review_signals_tools(catalog: ToolCatalog) -> ToolCatalog:
    return register_specs(catalog, REVIEW_SIGNALS_TOOLS)
