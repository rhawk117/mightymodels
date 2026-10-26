"""The investigation tools: thin async handlers over the sync use cases, and their registration.

investigation_start asks one form for the target's kind when the call leaves it out. A declined or
cancelled form returns the needs-input text as a normal result. Only add and knowns ask git, for
HEAD, and they ask before a use case opens its unit. The resolver's annotations are read at
runtime, so `KindAsk` is a module-level plain assignment and the request a runtime import.
"""

from typing import TYPE_CHECKING

from mcp.server.mcpserver.resolve import Elicit, Resolve
from mightymodels_core.investigations import (
    AddRequest,
    IncomingEntry,
    KnownsSelection,
    StartRequest,
)
from pydantic import BaseModel

from mightymodels_mcp.forms.choices import Choice, ChoiceQuestion, ChoiceRound, answers_of
from mightymodels_mcp.forms.needs_input import needs_input_text
from mightymodels_mcp.server.annotations import READS, WRITES
from mightymodels_mcp.server.registration import ToolSpec, open_tool_state, register_specs

from .schemas import (
    InvestigationAddRequest,
    InvestigationKnownsRequest,
    InvestigationListRequest,
    InvestigationRenderRequest,
    InvestigationStartRequest,
)
from .use_cases import (
    KnownsAtHead,
    add_to_investigation,
    create_investigation_work,
    list_investigations,
    render_investigation,
    show_knowns,
    start_investigation,
)
from .views import InvestigationView

if TYPE_CHECKING:
    from mightymodels_mcp.forms.choices import ChoiceOutcome
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext

    from .schemas import LedgerEntry

KIND = ChoiceQuestion(
    argument='kind',
    title='What kind of target is this?',
    description='What the investigation sets out to settle.',
    choices=(
        Choice(value='behavior', title='A behavior'),
        Choice(value='claim', title='A claim'),
        Choice(value='research', title='A research question'),
        Choice(value='change', title='A change'),
    ),
)

KindAsk = Elicit[BaseModel] | BaseModel


def kind_round(request: InvestigationStartRequest) -> ChoiceRound:
    message = f'What kind of target is this? {request.target}'
    return ChoiceRound(message=message, questions=(KIND,)).omitted_by(request)


def ask_kind(request: InvestigationStartRequest) -> KindAsk:
    return kind_round(request).ask()


KIND_RESOLVER = Resolve(ask_kind)


def incoming_entry(entry: LedgerEntry) -> IncomingEntry:
    return IncomingEntry(
        kind=entry.kind,
        text=entry.text,
        source=entry.source,
        cite=entry.cite,
        supersedes=entry.supersedes,
    )


async def investigation_start(
    request: InvestigationStartRequest, ctx: ToolContext, *, answers: ChoiceOutcome
) -> InvestigationView:
    """Start an investigation; asks the target's kind when the call omits it."""
    form = answers_of(answers)
    if form is None:
        return InvestigationView(text=needs_input_text(kind_round(request).questions))

    asked = StartRequest(target=request.target, kind=request.kind or form['kind'])
    async with open_tool_state(ctx) as state:
        return start_investigation(create_investigation_work(state), asked)


async def investigation_add(
    request: InvestigationAddRequest, ctx: ToolContext
) -> InvestigationView:
    """Add one round of entries to an investigation's ledger."""
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        entries = [incoming_entry(entry) for entry in request.entries]
        asked = AddRequest(round=request.round, entries=entries, head=head)
        work = create_investigation_work(state)
        return add_to_investigation(work, request.investigation_id, asked)


async def investigation_render(
    request: InvestigationRenderRequest, ctx: ToolContext
) -> InvestigationView:
    """Render an investigation's ledger; changes nothing."""
    async with open_tool_state(ctx) as state:
        return render_investigation(create_investigation_work(state), request.investigation_id)


async def investigation_knowns(
    request: InvestigationKnownsRequest, ctx: ToolContext
) -> InvestigationView:
    """Show the knowns table with each row current or a lead at HEAD; changes nothing."""
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        selection = KnownsSelection(kinds=request.kinds, limit=request.limit)
        asked = KnownsAtHead(investigation=request.investigation_id, selection=selection, head=head)
        return show_knowns(create_investigation_work(state), asked)


async def investigation_list(
    _request: InvestigationListRequest, ctx: ToolContext
) -> InvestigationView:
    """List the latest investigations with their rounds; changes nothing."""
    async with open_tool_state(ctx) as state:
        return list_investigations(create_investigation_work(state))


INVESTIGATION_TOOLS = (
    ToolSpec(
        name='investigation_start',
        title='Start an investigation',
        annotations=WRITES,
        icon='investigation',
        request_model=InvestigationStartRequest,
        result_model=InvestigationView,
        handler=investigation_start,
        resolvers={'answers': KIND_RESOLVER},
    ),
    ToolSpec(
        name='investigation_add',
        title="Add to an investigation's ledger",
        annotations=WRITES,
        icon='investigation',
        request_model=InvestigationAddRequest,
        result_model=InvestigationView,
        handler=investigation_add,
    ),
    ToolSpec(
        name='investigation_render',
        title="Show an investigation's ledger",
        annotations=READS,
        icon='investigation',
        request_model=InvestigationRenderRequest,
        result_model=InvestigationView,
        handler=investigation_render,
    ),
    ToolSpec(
        name='investigation_knowns',
        title='Show the knowns table',
        annotations=READS,
        icon='investigation',
        request_model=InvestigationKnownsRequest,
        result_model=InvestigationView,
        handler=investigation_knowns,
    ),
    ToolSpec(
        name='investigation_list',
        title='List investigations',
        annotations=READS,
        icon='investigation',
        request_model=InvestigationListRequest,
        result_model=InvestigationView,
        handler=investigation_list,
    ),
)


def register_investigation_tools(catalog: ToolCatalog) -> ToolCatalog:
    return register_specs(catalog, INVESTIGATION_TOOLS)
