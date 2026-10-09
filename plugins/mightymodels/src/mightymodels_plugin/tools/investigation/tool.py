"""The `investigation` tool: each handler checks the call's arguments and asks the service.

Every action but `start` and `list` works on one investigation, and `investigation_for` is the
one place that refuses a call that names none. `knowns` reads the whole table when the call
carries no filter.

`ResolvedInvestigations` is a plain assignment because the SDK does not see a `Resolve` marker
behind a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.investigation.schema import (
    InvestigationAction,
    InvestigationPayload,
    InvestigationStart,
    InvestigationView,
    KnownsFilter,
    LedgerRound,
)
from mightymodels_plugin.tools.investigation.service import InvestigationService
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)

INVESTIGATION_ARGUMENT = 'investigation_id'


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationCall:
    investigation_id: Slug | None
    payload: InvestigationPayload


def investigation_for(action: InvestigationAction, call: InvestigationCall) -> Slug:
    if call.investigation_id is None:
        raise MissingArgumentsError(action, INVESTIGATION_ARGUMENT)
    return call.investigation_id


def start_investigation(
    investigations: InvestigationService, call: InvestigationCall
) -> InvestigationView:
    if not isinstance(call.payload.request, InvestigationStart):
        raise MissingArgumentsError(InvestigationAction.START, 'a request holding target and kind')
    return investigations.start(call.payload.request, started=datetime.now(tz=UTC))


def add_entries(investigations: InvestigationService, call: InvestigationCall) -> InvestigationView:
    investigation = investigation_for(InvestigationAction.ADD, call)
    if call.payload.entries is None or not isinstance(call.payload.request, LedgerRound):
        raise MissingArgumentsError(InvestigationAction.ADD, 'entries and a request holding round')
    return investigations.add(investigation, call.payload.request.round, call.payload.entries)


def render_ledger(
    investigations: InvestigationService, call: InvestigationCall
) -> InvestigationView:
    return investigations.render(investigation_for(InvestigationAction.RENDER, call))


def render_knowns(
    investigations: InvestigationService, call: InvestigationCall
) -> InvestigationView:
    investigation = investigation_for(InvestigationAction.KNOWNS, call)
    selection = KnownsFilter() if call.payload.request is None else call.payload.request
    if not isinstance(selection, KnownsFilter):
        raise MissingArgumentsError(
            InvestigationAction.KNOWNS, 'no request, or a request holding only kinds and limit'
        )
    return investigations.knowns(investigation, selection)


def list_investigations(
    investigations: InvestigationService, _call: InvestigationCall
) -> InvestigationView:
    return investigations.listing()


def lifespan_investigations(ctx: Context[ServedState]) -> InvestigationService:
    return served_services(ctx).investigations


ResolvedInvestigations = Annotated[InvestigationService, Resolve(lifespan_investigations)]


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationTool:
    handlers: Mapping[
        InvestigationAction,
        ServiceHandler[InvestigationService, InvestigationCall, InvestigationView],
    ]

    def investigation(
        self,
        action: InvestigationAction,
        investigation_id: Slug | None = None,
        payload: InvestigationPayload | None = None,
        *,
        investigations: ResolvedInvestigations,
    ) -> InvestigationView:
        """Open an investigation, append ledger entries, or render the ledger or its knowns."""
        call = InvestigationCall(
            investigation_id=investigation_id,
            payload=InvestigationPayload() if payload is None else payload,
        )
        return dispatch_to_service(self.handlers, action, call, service=investigations)


investigation_tool = InvestigationTool(
    handlers=MappingProxyType(
        {
            InvestigationAction.START: start_investigation,
            InvestigationAction.ADD: add_entries,
            InvestigationAction.RENDER: render_ledger,
            InvestigationAction.KNOWNS: render_knowns,
            InvestigationAction.LIST: list_investigations,
        }
    )
)
investigation_action_tool: ActionTool[
    InvestigationAction, InvestigationService, InvestigationCall, InvestigationView
] = investigation_tool
