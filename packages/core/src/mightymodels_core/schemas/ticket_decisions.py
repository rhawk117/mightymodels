"""The decisions a user made through a dialog while working a ticket."""

from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Command, Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class AddTicketDecisionParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int
    question: str
    answer: str
    response: str | None
    note: str | None
    decided_at: int


class TicketDecisionsParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int


class TicketDecisionRow(Struct, frozen=True, kw_only=True, gc=False):
    question: str
    answer: str
    response: str | None
    note: str | None
    decided_at: int


ADD_TICKET_DECISION = Command(name='add_ticket_decision', params=AddTicketDecisionParams)
TICKET_DECISIONS = Query(
    name='ticket_decisions', params=TicketDecisionsParams, row=TicketDecisionRow
)

DECLARATIONS: tuple[Declaration, ...] = (ADD_TICKET_DECISION, TICKET_DECISIONS)
