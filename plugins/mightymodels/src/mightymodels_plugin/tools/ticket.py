"""The `ticket` tool."""

from collections.abc import Callable, Mapping
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
from mightymodels_plugin.tools.edge import ArgumentsError, tool_checkout

type TicketHandler = Callable[[Checkout, Slug, TicketFields | None], TicketView]


def write(checkout: Checkout, slug: Slug, fields: TicketFields | None) -> TicketView:
    if not isinstance(fields, TicketAnswers):
        raise ArgumentsError(TicketAction.WRITE, 'fields holding the interview answers')
    return service.write(checkout, slug, fields)


def validate(checkout: Checkout, slug: Slug, _fields: TicketFields | None) -> TicketView:
    return service.validate(checkout, slug)


def show(checkout: Checkout, slug: Slug, _fields: TicketFields | None) -> TicketView:
    return service.show(checkout, slug)


def update_context(checkout: Checkout, slug: Slug, fields: TicketFields | None) -> TicketView:
    if not isinstance(fields, TicketContext):
        raise ArgumentsError(TicketAction.UPDATE_CONTEXT, 'fields holding only the context lines')
    return service.update_context(checkout, slug, fields)


HANDLERS: Mapping[TicketAction, TicketHandler] = MappingProxyType(
    {
        TicketAction.WRITE: write,
        TicketAction.VALIDATE: validate,
        TicketAction.SHOW: show,
        TicketAction.UPDATE_CONTEXT: update_context,
    }
)


def ticket(action: TicketAction, slug: Slug, fields: TicketFields | None = None) -> TicketView:
    """Create, validate, read or update a ticket's context lines; derives model routing by scope."""
    with tool_checkout() as checkout:
        return HANDLERS[action](checkout, slug, fields)
