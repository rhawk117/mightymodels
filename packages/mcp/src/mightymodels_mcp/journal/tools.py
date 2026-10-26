"""The journal tools: thin async handlers over the sync use cases, and their registration.

None of the four asks git: core's journal takes no HEAD. A core refusal reaches the agent as an
error through registration.
"""

from typing import TYPE_CHECKING

from mightymodels_core.crashouts import CrashoutEntry

from mightymodels_mcp.server.annotations import READS, WRITES
from mightymodels_mcp.server.registration import ToolSpec, open_tool_state, register_specs

from .schemas import (
    CrashoutAddRequest,
    CrashoutLastRequest,
    CrashoutStatsRequest,
    SimilaritySearchRequest,
)
from .use_cases import (
    SimilarityQuery,
    add_crashout,
    create_journal_work,
    search_similar,
    show_crashout_stats,
    show_last_crashout,
)
from .views import JournalView

if TYPE_CHECKING:
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext


def crashout_entry(request: CrashoutAddRequest) -> CrashoutEntry:
    return CrashoutEntry(
        ticket_key=request.ticket,
        branch=request.branch,
        severity=request.severity,
        verdict=request.verdict,
        rant=request.rant,
        failures=request.failures,
        root_cause=request.root_cause,
        corrective_action=request.corrective_action,
        barked_back=request.barked_back,
    )


async def crashout_add(request: CrashoutAddRequest, ctx: ToolContext) -> JournalView:
    """Journal one crashout; a blank field or an empty list of failures is refused."""
    async with open_tool_state(ctx) as state:
        return add_crashout(create_journal_work(state), crashout_entry(request))


async def crashout_stats(_request: CrashoutStatsRequest, ctx: ToolContext) -> JournalView:
    """Show the patterns across the latest crashouts; changes nothing."""
    async with open_tool_state(ctx) as state:
        return show_crashout_stats(create_journal_work(state))


async def crashout_last(_request: CrashoutLastRequest, ctx: ToolContext) -> JournalView:
    """Show the newest crashout; changes nothing."""
    async with open_tool_state(ctx) as state:
        return show_last_crashout(create_journal_work(state))


async def similarity_search(request: SimilaritySearchRequest, ctx: ToolContext) -> JournalView:
    """Search the journaled rows for text like the query; changes nothing."""
    async with open_tool_state(ctx) as state:
        asked = SimilarityQuery(query=request.query, kind=request.kind)
        return search_similar(create_journal_work(state), asked)


JOURNAL_TOOLS = (
    ToolSpec(
        name='crashout_add',
        title='Journal a crashout',
        annotations=WRITES,
        icon='crashout',
        request_model=CrashoutAddRequest,
        result_model=JournalView,
        handler=crashout_add,
    ),
    ToolSpec(
        name='crashout_stats',
        title='Show crashout patterns',
        annotations=READS,
        icon='crashout',
        request_model=CrashoutStatsRequest,
        result_model=JournalView,
        handler=crashout_stats,
    ),
    ToolSpec(
        name='crashout_last',
        title='Show the last crashout',
        annotations=READS,
        icon='crashout',
        request_model=CrashoutLastRequest,
        result_model=JournalView,
        handler=crashout_last,
    ),
    ToolSpec(
        name='similarity_search',
        title='Search for similar rows',
        annotations=READS,
        icon='similarity',
        request_model=SimilaritySearchRequest,
        result_model=JournalView,
        handler=similarity_search,
    ),
)


def register_journal_tools(catalog: ToolCatalog) -> ToolCatalog:
    return register_specs(catalog, JOURNAL_TOOLS)
