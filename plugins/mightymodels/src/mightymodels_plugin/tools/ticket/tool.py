"""The `ticket` tool."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.models.slug import Slug
from mightymodels_plugin.models.ticket import (
    TicketAction,
    TicketAnswers,
    TicketContext,
    TicketFields,
    TicketView,
)
from mightymodels_plugin.services import ticket as service
from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    MissingArgumentsError,
    ResolvedCheckouts,
    dispatch_action,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketCall:
    slug: Slug
    fields: TicketFields | None


def write_ticket(checkout: Checkout, call: TicketCall) -> TicketView:
    if not isinstance(call.fields, TicketAnswers):
        raise MissingArgumentsError(TicketAction.WRITE, 'fields holding the interview answers')
    return service.write(checkout, call.slug, call.fields)


def validate_ticket(checkout: Checkout, call: TicketCall) -> TicketView:
    return service.validate(checkout, call.slug)


def show_ticket(checkout: Checkout, call: TicketCall) -> TicketView:
    return service.show(checkout, call.slug)


def update_ticket_context(checkout: Checkout, call: TicketCall) -> TicketView:
    if not isinstance(call.fields, TicketContext):
        raise MissingArgumentsError(
            TicketAction.UPDATE_CONTEXT, 'fields holding only the context lines'
        )
    return service.update_context(checkout, call.slug, call.fields)


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketTool:
    handlers: Mapping[TicketAction, ActionHandler[TicketCall, TicketView]]

    def ticket(
        self,
        action: TicketAction,
        slug: Slug,
        fields: TicketFields | None = None,
        *,
        checkouts: ResolvedCheckouts,
    ) -> TicketView:
        """Create, validate, read or update a ticket's context lines; derives model routing by scope."""  # noqa: E501 - the SDK serves this line as the tool description and the schema snapshot pins its text
        call = TicketCall(slug=slug, fields=fields)
        return dispatch_action(self.handlers, action, call, checkouts=checkouts)


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
