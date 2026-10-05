"""The `review` tool: each handler checks the call's arguments and asks the review service.

Every action but `start` and `list` works on one run, and `run_id_for` is the one place that
refuses a call that names none.

`ResolvedReviews` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.run_id import RunId
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    LifespanState,
    MissingArgumentsError,
    ServiceHandler,
    dispatch_to_service,
)
from mightymodels_plugin.tools.review.schema import (
    AddPayload,
    DisposePayload,
    ReportPayload,
    ResolvePayload,
    ReviewAction,
    ReviewPayload,
    ReviewView,
    StartPayload,
)
from mightymodels_plugin.tools.review.service import ReviewService

RUN_ID_ARGUMENT = 'run_id'


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewCall:
    run_id: RunId | None
    payload: ReviewPayload | None


def run_id_for(action: ReviewAction, call: ReviewCall) -> RunId:
    if call.run_id is None:
        raise MissingArgumentsError(action, RUN_ID_ARGUMENT)
    return call.run_id


def start_run(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    if not isinstance(call.payload, StartPayload):
        raise MissingArgumentsError(
            ReviewAction.START, 'a payload holding scope, depth and emphasis'
        )
    return reviews.start(call.payload, started=datetime.now(tz=UTC))


def add_persona_report(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    run = run_id_for(ReviewAction.ADD, call)
    if not isinstance(call.payload, AddPayload):
        raise MissingArgumentsError(
            ReviewAction.ADD, 'a payload holding the persona whose report to read'
        )
    return reviews.add(run, call.payload.persona)


def gate_run(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    return reviews.gate(run_id_for(ReviewAction.GATE, call))


def dispose_findings(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    run = run_id_for(ReviewAction.DISPOSE, call)
    if not isinstance(call.payload, DisposePayload):
        raise MissingArgumentsError(ReviewAction.DISPOSE, 'a payload holding by and decisions')
    return reviews.dispose(run, call.payload)


def resolve_finding(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    run = run_id_for(ReviewAction.RESOLVE, call)
    if not isinstance(call.payload, ResolvePayload):
        raise MissingArgumentsError(ReviewAction.RESOLVE, 'a payload holding finding and result')
    return reviews.resolve(run, call.payload)


def render_report(reviews: ReviewService, call: ReviewCall) -> ReviewView:
    run = run_id_for(ReviewAction.REPORT, call)
    payload = call.payload if isinstance(call.payload, ReportPayload) else ReportPayload()
    return reviews.report(run, payload.shape)


def list_runs(reviews: ReviewService, _call: ReviewCall) -> ReviewView:
    return reviews.listing()


def lifespan_reviews(ctx: Context[LifespanState]) -> ReviewService:
    return ctx.request_context.lifespan_context.reviews


ResolvedReviews = Annotated[ReviewService, Resolve(lifespan_reviews)]


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewTool:
    handlers: Mapping[ReviewAction, ServiceHandler[ReviewService, ReviewCall, ReviewView]]

    def review(
        self,
        action: ReviewAction,
        run_id: RunId | None = None,
        payload: ReviewPayload | None = None,
        *,
        reviews: ResolvedReviews,
    ) -> ReviewView:
        """Record a review run, its findings, dispositions and resolutions; render the report text."""  # noqa: E501 - the SDK serves this line as the tool description and the schema snapshot pins its text
        call = ReviewCall(run_id=run_id, payload=payload)
        return dispatch_to_service(self.handlers, action, call, service=reviews)


review_tool = ReviewTool(
    handlers=MappingProxyType(
        {
            ReviewAction.START: start_run,
            ReviewAction.ADD: add_persona_report,
            ReviewAction.GATE: gate_run,
            ReviewAction.DISPOSE: dispose_findings,
            ReviewAction.RESOLVE: resolve_finding,
            ReviewAction.REPORT: render_report,
            ReviewAction.LIST: list_runs,
        }
    )
)
review_action_tool: ActionTool[ReviewAction, ReviewService, ReviewCall, ReviewView] = review_tool
