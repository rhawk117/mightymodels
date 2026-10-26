"""The review run tools: thin async handlers over the sync use cases, and their registration.

review_start asks one form for the scope, depth and emphasis the call leaves out, and asks git
only for HEAD. A declined or cancelled form returns the needs-input text as a normal result. The
other five tools ask git nothing. The resolver's annotations are read at runtime, so `RoundAsk` is
a module-level plain assignment and `ReviewStartRequest` a runtime import.
"""

from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver.resolve import Elicit, Resolve
from mightymodels_core.reviews import StartRequest
from mightymodels_core.workspace import workspace_at
from pydantic import BaseModel

from mightymodels_mcp.forms.choices import Choice, ChoiceQuestion, ChoiceRound, answers_of
from mightymodels_mcp.forms.needs_input import needs_input_text
from mightymodels_mcp.server.annotations import READS, WRITES
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolDefinition, open_tool_state

from .schemas import (
    ReviewAddRequest,
    ReviewGateRequest,
    ReviewListRequest,
    ReviewOverrideRequest,
    ReviewReportRequest,
    ReviewStartRequest,
)
from .use_cases import (
    ReportToAdd,
    StartAtHead,
    add_review_findings,
    create_review_work,
    gate_review,
    list_reviews,
    override_review,
    report_review,
    start_review,
)
from .views import ReviewView

if TYPE_CHECKING:
    from mightymodels_mcp.forms.choices import ChoiceOutcome
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext

SCOPE = ChoiceQuestion(
    argument='scope',
    title='What should the review cover?',
    description='The part of the repository the review reads.',
    choices=(
        Choice(value='diff', title='The diff'),
        Choice(value='branch', title='The branch against a base'),
        Choice(value='ticket', title="The ticket's branch against a base"),
        Choice(value='codebase', title='The whole codebase'),
    ),
)
DEPTH = ChoiceQuestion(
    argument='depth',
    title='How deep should the review go?',
    description='How many reviewers read the scope, and on which models.',
    choices=(
        Choice(value='quick', title='Quick'),
        Choice(value='standard', title='Standard'),
        Choice(value='deep', title='Deep'),
    ),
)
EMPHASIS = ChoiceQuestion(
    argument='emphasis',
    title='What should the review emphasize?',
    description='How the reviewers are weighted against each other.',
    choices=(
        Choice(value='release-readiness', title='Release readiness'),
        Choice(value='maintainability', title='Maintainability'),
        Choice(value='balanced', title='Balanced'),
        Choice(value='custom', title='Custom weights'),
    ),
)
START_ROUND = ChoiceRound(
    message='Answer what the review still needs', questions=(SCOPE, DEPTH, EMPHASIS)
)


RoundAsk = Elicit[BaseModel] | BaseModel


def ask_start_round(request: ReviewStartRequest) -> RoundAsk:
    return START_ROUND.omitted_by(request).ask()


START_ROUND_RESOLVER = Resolve(ask_start_round)


def describe_unanswered(request: ReviewStartRequest) -> str:
    return needs_input_text(START_ROUND.omitted_by(request).questions)


def named_weights(request: ReviewStartRequest) -> dict[str, float] | None:
    if request.weights is None:
        return None

    named: dict[str, float] = dict(request.weights.items())
    return named


def create_start_request(request: ReviewStartRequest, form: dict[str, Any]) -> StartRequest:
    return StartRequest(
        scope=request.scope or form['scope'],
        base=request.base,
        slug=request.slug,
        depth=request.depth or form['depth'],
        emphasis=request.emphasis or form['emphasis'],
        weights=named_weights(request),
        persona=request.persona,
    )


async def review_start(
    request: ReviewStartRequest, ctx: ToolContext, *, answers: ChoiceOutcome
) -> ReviewView:
    """Start a review run; asks the scope, depth and emphasis the call omits."""
    form = answers_of(answers)
    if form is None:
        return ReviewView(text=describe_unanswered(request))

    start = create_start_request(request, form)
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        workspace = workspace_at(state.checkout.toplevel)
        return start_review(
            create_review_work(state), workspace, StartAtHead(request=start, head=head)
        )


async def review_override(request: ReviewOverrideRequest, ctx: ToolContext) -> ReviewView:
    """Switch a run's heavier reviewer to the override model."""
    async with open_tool_state(ctx) as state:
        return override_review(create_review_work(state), request.run_id)


async def review_add(request: ReviewAddRequest, ctx: ToolContext) -> ReviewView:
    """Read a reviewer's report from the run's directory and record its findings."""
    async with open_tool_state(ctx) as state:
        workspace = workspace_at(state.checkout.toplevel)
        work = create_review_work(state)
        report = ReportToAdd(run_id=request.run_id, persona=request.persona)
        return add_review_findings(work, workspace, report)


async def review_gate(request: ReviewGateRequest, ctx: ToolContext) -> ReviewView:
    """List a run's findings in gate order with each one's decision; changes nothing."""
    async with open_tool_state(ctx) as state:
        return gate_review(create_review_work(state), request.run_id)


async def review_report(request: ReviewReportRequest, ctx: ToolContext) -> ReviewView:
    """Render a run's report, in full or as a review comment; changes nothing."""
    async with open_tool_state(ctx) as state:
        return report_review(create_review_work(state), request.run_id, request.shape)


async def review_list(_request: ReviewListRequest, ctx: ToolContext) -> ReviewView:
    """List the latest review runs with their findings and verdicts; changes nothing."""
    async with open_tool_state(ctx) as state:
        return list_reviews(create_review_work(state))


def register_review_tools(catalog: ToolCatalog) -> ToolCatalog:
    icon = load_icon('review')
    start = ToolDefinition(
        name='review_start',
        title='Start a review',
        annotations=WRITES,
        icon=icon,
        request_model=ReviewStartRequest,
        result_model=ReviewView,
        handler=review_start,
        resolvers={'answers': START_ROUND_RESOLVER},
    )
    override = ToolDefinition(
        name='review_override',
        title="Override a review's models",
        annotations=WRITES,
        icon=icon,
        request_model=ReviewOverrideRequest,
        result_model=ReviewView,
        handler=review_override,
    )
    add = ToolDefinition(
        name='review_add',
        title="Add a reviewer's report",
        annotations=WRITES,
        icon=icon,
        request_model=ReviewAddRequest,
        result_model=ReviewView,
        handler=review_add,
    )
    gate = ToolDefinition(
        name='review_gate',
        title='Gate a review',
        annotations=READS,
        icon=icon,
        request_model=ReviewGateRequest,
        result_model=ReviewView,
        handler=review_gate,
    )
    report = ToolDefinition(
        name='review_report',
        title='Report a review',
        annotations=READS,
        icon=icon,
        request_model=ReviewReportRequest,
        result_model=ReviewView,
        handler=review_report,
    )
    listing = ToolDefinition(
        name='review_list',
        title='List the reviews',
        annotations=READS,
        icon=icon,
        request_model=ReviewListRequest,
        result_model=ReviewView,
        handler=review_list,
    )
    opened = catalog.register(start).register(override).register(add)
    return opened.register(gate).register(report).register(listing)
