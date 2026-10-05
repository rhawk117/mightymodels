"""The `review` tool."""

from collections.abc import Callable, Mapping
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
from mightymodels_plugin.tools.edge import ArgumentsError, tool_checkout


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewCall:
    run_id: RunId | None
    payload: ReviewPayload | None


type ReviewHandler = Callable[[Checkout, ReviewCall], ReviewView]


def run_of(action: ReviewAction, call: ReviewCall) -> RunId:
    if call.run_id is None:
        raise ArgumentsError(action, 'run_id')
    return call.run_id


def start(checkout: Checkout, call: ReviewCall) -> ReviewView:
    if not isinstance(call.payload, StartPayload):
        raise ArgumentsError(ReviewAction.START, 'a payload holding scope, depth and emphasis')
    return service.start(checkout, call.payload, started=datetime.now(tz=UTC))


def add(checkout: Checkout, call: ReviewCall) -> ReviewView:
    run = run_of(ReviewAction.ADD, call)
    if not isinstance(call.payload, AddPayload):
        raise ArgumentsError(ReviewAction.ADD, 'a payload holding the persona whose report to read')
    return service.add(checkout, run, call.payload.persona)


def gate(checkout: Checkout, call: ReviewCall) -> ReviewView:
    return service.gate(checkout, run_of(ReviewAction.GATE, call))


def dispose(checkout: Checkout, call: ReviewCall) -> ReviewView:
    run = run_of(ReviewAction.DISPOSE, call)
    if not isinstance(call.payload, DisposePayload):
        raise ArgumentsError(ReviewAction.DISPOSE, 'a payload holding by and decisions')
    return service.dispose(checkout, run, call.payload)


def resolve(checkout: Checkout, call: ReviewCall) -> ReviewView:
    run = run_of(ReviewAction.RESOLVE, call)
    if not isinstance(call.payload, ResolvePayload):
        raise ArgumentsError(ReviewAction.RESOLVE, 'a payload holding finding and result')
    return service.resolve(checkout, run, call.payload)


def report(checkout: Checkout, call: ReviewCall) -> ReviewView:
    run = run_of(ReviewAction.REPORT, call)
    payload = call.payload if isinstance(call.payload, ReportPayload) else ReportPayload()
    return service.report(checkout, run, payload.shape)


def listing(checkout: Checkout, _call: ReviewCall) -> ReviewView:
    return service.listing(checkout)


HANDLERS: Mapping[ReviewAction, ReviewHandler] = MappingProxyType(
    {
        ReviewAction.START: start,
        ReviewAction.ADD: add,
        ReviewAction.GATE: gate,
        ReviewAction.DISPOSE: dispose,
        ReviewAction.RESOLVE: resolve,
        ReviewAction.REPORT: report,
        ReviewAction.LIST: listing,
    }
)


def review(
    action: ReviewAction, run_id: RunId | None = None, payload: ReviewPayload | None = None
) -> ReviewView:
    """Record a review run, its findings, dispositions and resolutions; render the report text."""
    with tool_checkout() as checkout:
        return HANDLERS[action](checkout, ReviewCall(run_id=run_id, payload=payload))
