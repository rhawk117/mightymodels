"""The ticket decision repository kept in memory."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.ticket_decisions import TicketDecision

if TYPE_CHECKING:
    from datetime import datetime

    from mightymodels_core.ticket_decisions import IncomingDecision


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeTicketDecisionRepository:
    decided_at: datetime
    held: dict[int, list[TicketDecision]] = field(default_factory=dict)

    def add(self, ticket_id: int, decision: IncomingDecision) -> None:
        self.held.setdefault(ticket_id, []).append(
            TicketDecision(
                question=decision.question,
                answer=decision.answer,
                response=decision.response,
                note=decision.note,
                decided_at=self.decided_at,
            )
        )

    def decisions(self, ticket_id: int) -> tuple[TicketDecision, ...]:
        return tuple(self.held.get(ticket_id, ()))
