"""The `ticket` tool: each handler checks the call's arguments and asks the ticket service.

`ResolvedTickets` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    MissingArgumentsError,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels_plugin.tools.ticket.schema import (
    TicketAction,
    TicketAnswers,
    TicketContext,
    TicketFields,
    TicketView,
)
from mightymodels_plugin.tools.ticket.service import TicketService


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketCall:
    slug: Slug
    fields: TicketFields | None


def write_ticket(tickets: TicketService, call: TicketCall) -> TicketView:
    if not isinstance(call.fields, TicketAnswers):
        raise MissingArgumentsError(TicketAction.WRITE, 'fields holding the interview answers')
    return tickets.write(call.slug, call.fields)


def validate_ticket(tickets: TicketService, call: TicketCall) -> TicketView:
    return tickets.validate(call.slug)


def show_ticket(tickets: TicketService, call: TicketCall) -> TicketView:
    return tickets.show(call.slug)


def update_ticket_context(tickets: TicketService, call: TicketCall) -> TicketView:
    if not isinstance(call.fields, TicketContext):
        raise MissingArgumentsError(
            TicketAction.UPDATE_CONTEXT, 'fields holding only the context lines'
        )
    return tickets.update_context(call.slug, call.fields)


def lifespan_tickets(ctx: Context[ServedState]) -> TicketService:
    return served_services(ctx).tickets


ResolvedTickets = Annotated[TicketService, Resolve(lifespan_tickets)]


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketTool:
    handlers: Mapping[TicketAction, ServiceHandler[TicketService, TicketCall, TicketView]]

    def ticket(
        self,
        action: TicketAction,
        slug: Slug,
        fields: TicketFields | None = None,
        *,
        tickets: ResolvedTickets,
    ) -> TicketView:
        """Create, validate, read or update a ticket's context lines; routes models by scope."""
        call = TicketCall(slug=slug, fields=fields)
        return dispatch_to_service(self.handlers, action, call, service=tickets)


ticket_tool = TicketTool(
    handlers=MappingProxyType(
        {
            TicketAction.WRITE: write_ticket,
            TicketAction.VALIDATE: validate_ticket,
            TicketAction.SHOW: show_ticket,
            TicketAction.UPDATE_CONTEXT: update_ticket_context,
        }
    )
)
ticket_action_tool: ActionTool[TicketAction, TicketService, TicketCall, TicketView] = ticket_tool
