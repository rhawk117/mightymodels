"""The seam under the ticket decision services: the decisions recorded on one ticket."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mightymodels_core.ticket_decisions.records import IncomingDecision, TicketDecision


@runtime_checkable
class TicketDecisionRepository(Protocol):
    def add(self, ticket_id: int, decision: IncomingDecision) -> None: ...

    def decisions(self, ticket_id: int) -> tuple[TicketDecision, ...]: ...
