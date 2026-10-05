"""The `review` tool."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.models.review import (
    AddPayload,
    DisposePayload,
    ReportPayload,
    ResolvePayload,
    ReviewAction,
    ReviewPayload,
    ReviewView,
    StartPayload,
)
from mightymodels_plugin.models.run_id import RunId
from mightymodels_plugin.services import review as service
from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    MissingArgumentsError,
    ResolvedCheckouts,
    dispatch_action,
)

RUN_ID_ARGUMENT = 'run_id'


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewCall:
    run_id: RunId | None
    payload: ReviewPayload | None


def start_run(checkout: Checkout, call: ReviewCall) -> ReviewView:
    if not isinstance(call.payload, StartPayload):
        raise MissingArgumentsError(
            ReviewAction.START, 'a payload holding scope, depth and emphasis'
        )
    return service.start(checkout, call.payload, started=datetime.now(tz=UTC))


def add_persona_report(checkout: Checkout, call: ReviewCall) -> ReviewView:
    if call.run_id is None:
        raise MissingArgumentsError(ReviewAction.ADD, RUN_ID_ARGUMENT)
    if not isinstance(call.payload, AddPayload):
        raise MissingArgumentsError(
            ReviewAction.ADD, 'a payload holding the persona whose report to read'
        )
    return service.add(checkout, call.run_id, call.payload.persona)


def gate_run(checkout: Checkout, call: ReviewCall) -> ReviewView:
    if call.run_id is None:
        raise MissingArgumentsError(ReviewAction.GATE, RUN_ID_ARGUMENT)
    return service.gate(checkout, call.run_id)


def dispose_findings(checkout: Checkout, call: ReviewCall) -> ReviewView:
    if call.run_id is None:
        raise MissingArgumentsError(ReviewAction.DISPOSE, RUN_ID_ARGUMENT)
    if not isinstance(call.payload, DisposePayload):
        raise MissingArgumentsError(ReviewAction.DISPOSE, 'a payload holding by and decisions')
    return service.dispose(checkout, call.run_id, call.payload)


def resolve_finding(checkout: Checkout, call: ReviewCall) -> ReviewView:
    if call.run_id is None:
        raise MissingArgumentsError(ReviewAction.RESOLVE, RUN_ID_ARGUMENT)
    if not isinstance(call.payload, ResolvePayload):
        raise MissingArgumentsError(ReviewAction.RESOLVE, 'a payload holding finding and result')
    return service.resolve(checkout, call.run_id, call.payload)


def render_report(checkout: Checkout, call: ReviewCall) -> ReviewView:
    if call.run_id is None:
        raise MissingArgumentsError(ReviewAction.REPORT, RUN_ID_ARGUMENT)
    payload = call.payload if isinstance(call.payload, ReportPayload) else ReportPayload()
    return service.report(checkout, call.run_id, payload.shape)


def list_runs(checkout: Checkout, _call: ReviewCall) -> ReviewView:
    return service.listing(checkout)


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewTool:
    handlers: Mapping[ReviewAction, ActionHandler[ReviewCall, ReviewView]]

    def review(
        self,
        action: ReviewAction,
        run_id: RunId | None = None,
        payload: ReviewPayload | None = None,
        *,
        checkouts: ResolvedCheckouts,
    ) -> ReviewView:
        """Record a review run, its findings, dispositions and resolutions; render the report text."""  # noqa: E501 - the SDK serves this line as the tool description and the schema snapshot pins its text
        call = ReviewCall(run_id=run_id, payload=payload)
        return dispatch_action(self.handlers, action, call, checkouts=checkouts)


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
