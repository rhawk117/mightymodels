"""The review decision tools: review_dispose decides a run's findings, review_resolve their fixes.

review_dispose given no decisions asks in one call through a chain of resolvers: the run's
undecided findings, one page of at most ten of them as checkboxes, then a reasons form for each box
left unchecked. A last resolver turns the answers into dispositions, so the handler takes a single
outcome. A declined or cancelled round records nothing, not even the checked boxes, and returns the
needs-input text as a normal result. Neither tool asks git anything.

The SDK reads a resolver's annotations at runtime and knows a context only as a `Context` class,
never through a `type` alias, so the context, the outcomes and the asks are module-level plain
assignments. A refusal from core inside a resolver becomes the tool error carrying core's message
through the same wrapper a handler gets when the tool is registered.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from mcp.server.elicitation import AcceptedElicitation
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mightymodels_core.reviews import IncomingDisposition, ResolveRequest
from pydantic import BaseModel, ConfigDict, Field

from mightymodels_mcp.forms.choices import Choice, ChoiceOutcome, ChoiceQuestion
from mightymodels_mcp.forms.dispose import ReasonsForm, create_dispose_pages
from mightymodels_mcp.forms.needs_input import needs_input_text
from mightymodels_mcp.server.annotations import WRITES
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolDefinition, open_tool_state
from mightymodels_mcp.server.requests import USER_APPROVER

from .schemas import Disposition, ReviewDisposeRequest, ReviewResolveRequest
from .use_cases import (
    DispositionsToRecord,
    create_review_work,
    dispose_findings,
    list_undecided,
    resolve_finding,
)
from .views import ReviewView

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.primitives import RunId
    from mightymodels_core.reviews import FindingRecord

    from mightymodels_mcp.forms.dispose import DisposePage
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext

DISPOSE_CHOICES = (
    Choice(value='fix', title='Fix'),
    Choice(value='defer', title='Defer'),
    Choice(value='accept-risk', title='Accept the risk'),
    Choice(value='dismiss', title='Dismiss'),
)
DISPOSE_PROMPT = 'decisions {"F…": {"decision": <choice>, "reason": "<why>"}}'
FIX = Disposition(decision='fix')

ResolverContext = Context[ServerDependencies, Any]
FormAsk = Elicit[BaseModel] | None


class DisposeChoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    decisions: dict[str, Disposition] = Field(default_factory=dict)
    unanswered: tuple[str, ...] | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class UndecidedFindings:
    run_id: RunId
    findings: tuple[FindingRecord, ...]

    @property
    def page(self) -> DisposePage | None:
        message = (
            f'Check the findings of {self.run_id} to fix; '
            'each one left unchecked gets a decision next'
        )
        pages = create_dispose_pages(message, self.findings)
        return pages[0] if pages else None

    def reasons_form(self, page: DisposePage, answers: BaseModel) -> ReasonsForm | None:
        unchecked = page.select(answers, checked=False)
        if not unchecked:
            return None

        message = (
            f'Decide each unchecked finding of {self.run_id}: '
            'defer, accept the risk or dismiss, and why'
        )
        return ReasonsForm(message=message, findings=unchecked)


def unanswered(page: DisposePage) -> DisposeChoice:
    return DisposeChoice(unanswered=tuple(finding.key for finding in page.findings))


def unanswered_question(keys: tuple[str, ...]) -> ChoiceQuestion:
    return ChoiceQuestion(
        argument='decisions',
        prompt=DISPOSE_PROMPT,
        title=f'What should happen to {", ".join(keys)}? accept-risk and dismiss need a reason.',
        description='How each finding is decided, and why.',
        choices=DISPOSE_CHOICES,
    )


async def find_undecided(request: ReviewDisposeRequest, ctx: ResolverContext) -> UndecidedFindings:
    if request.decisions is not None:
        return UndecidedFindings(run_id=request.run_id, findings=())

    async with open_tool_state(ctx) as state:
        findings = list_undecided(create_review_work(state), request.run_id)

    return UndecidedFindings(run_id=request.run_id, findings=findings)


UNDECIDED_RESOLVER = Resolve(find_undecided)
UndecidedOutcome = Annotated[UndecidedFindings, UNDECIDED_RESOLVER]


def ask_page(undecided: UndecidedOutcome) -> FormAsk:
    page = undecided.page
    return None if page is None else page.ask()


PAGE_RESOLVER = Resolve(ask_page)
PageOutcome = Annotated[ChoiceOutcome, PAGE_RESOLVER]


def ask_reasons(undecided: UndecidedOutcome, page: PageOutcome) -> FormAsk:
    shown = undecided.page
    if shown is None or not isinstance(page, AcceptedElicitation):
        return None

    form = undecided.reasons_form(shown, page.data)
    return None if form is None else form.ask()


REASONS_RESOLVER = Resolve(ask_reasons)
ReasonsOutcome = Annotated[ChoiceOutcome, REASONS_RESOLVER]


def choose_dispositions(
    undecided: UndecidedOutcome, page: PageOutcome, reasons: ReasonsOutcome
) -> DisposeChoice:
    shown = undecided.page
    if shown is None:
        return DisposeChoice()

    if not isinstance(page, AcceptedElicitation):
        return unanswered(shown)

    fixes = {finding.key: FIX for finding in shown.select(page.data, checked=True)}
    form = undecided.reasons_form(shown, page.data)
    if form is None:
        return DisposeChoice(decisions=fixes)

    if not isinstance(reasons, AcceptedElicitation):
        return unanswered(shown)

    reasoned = {
        entry.finding_key: Disposition(decision=entry.decision, reason=entry.reason)
        for entry in form.read(reasons.data)
    }
    return DisposeChoice(decisions=fixes | reasoned)


CHOSEN_RESOLVER = Resolve(choose_dispositions)


@dataclass(slots=True, kw_only=True, frozen=True)
class DecidedBy:
    decisions: Mapping[str, Disposition]
    by: str


def decided_by(request: ReviewDisposeRequest, choice: DisposeChoice) -> DecidedBy:
    if request.decisions is None:
        return DecidedBy(decisions=choice.decisions, by=USER_APPROVER)

    return DecidedBy(decisions=request.decisions, by=request.by)


def create_dispositions(run_id: RunId, decided: DecidedBy) -> DispositionsToRecord:
    decisions = {
        key: IncomingDisposition(decision=entry.decision, reason=entry.reason)
        for key, entry in decided.decisions.items()
    }
    return DispositionsToRecord(run_id=run_id, decisions=decisions, by=decided.by)


async def review_dispose(
    request: ReviewDisposeRequest, ctx: ToolContext, *, chosen: AcceptedElicitation[DisposeChoice]
) -> ReviewView:
    """Decide a run's findings; asks a page of them to fix, then why for each one left unchecked."""
    choice = chosen.data
    if choice.unanswered is not None:
        text = needs_input_text((unanswered_question(choice.unanswered),))
        return ReviewView(text=text, run_id=request.run_id)

    dispositions = create_dispositions(request.run_id, decided_by(request, choice))
    async with open_tool_state(ctx) as state:
        return dispose_findings(create_review_work(state), dispositions)


async def review_resolve(request: ReviewResolveRequest, ctx: ToolContext) -> ReviewView:
    """Record how a finding chosen for fix turned out: fixed at a commit, failed or blocked."""
    resolve = ResolveRequest(
        finding_key=request.finding,
        result=request.result,
        commit=request.commit,
        reason=request.reason,
    )
    async with open_tool_state(ctx) as state:
        return resolve_finding(create_review_work(state), request.run_id, resolve)


def register_decision_tools(catalog: ToolCatalog) -> ToolCatalog:
    icon = load_icon('review')
    dispose = ToolDefinition(
        name='review_dispose',
        title="Decide a review's findings",
        annotations=WRITES,
        icon=icon,
        request_model=ReviewDisposeRequest,
        result_model=ReviewView,
        handler=review_dispose,
        resolvers={'chosen': CHOSEN_RESOLVER},
    )
    resolve = ToolDefinition(
        name='review_resolve',
        title='Resolve a review finding',
        annotations=WRITES,
        icon=icon,
        request_model=ReviewResolveRequest,
        result_model=ReviewView,
        handler=review_resolve,
    )
    return catalog.register(dispose).register(resolve)
