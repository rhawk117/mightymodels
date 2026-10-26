"""The ticket decision repository over a core unit, taking the ticket id per call."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import from_unixepoch
from mightymodels_core.schemas.ticket_decisions import (
    ADD_TICKET_DECISION,
    TICKET_DECISIONS,
    AddTicketDecisionParams,
    TicketDecisionsParams,
)
from mightymodels_core.ticket_decisions.records import IncomingDecision, TicketDecision

if TYPE_CHECKING:
    from mightymodels_core.database import Unit
    from mightymodels_core.primitives import Clock
    from mightymodels_core.schemas.ticket_decisions import TicketDecisionRow


def decision_of(row: TicketDecisionRow) -> TicketDecision:
    stored = IncomingDecision(
        question=row.question, answer=row.answer, response=row.response, note=row.note
    ).redacted()
    return TicketDecision(
        question=stored.question,
        answer=stored.answer,
        response=stored.response,
        note=stored.note,
        decided_at=from_unixepoch(row.decided_at),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteTicketDecisionRepository:
    unit: Unit
    clock: Clock

    def add(self, ticket_id: int, decision: IncomingDecision) -> None:
        stored = decision.redacted()
        params = AddTicketDecisionParams(
            ticket_id=ticket_id,
            question=stored.question,
            answer=stored.answer,
            response=stored.response,
            note=stored.note,
            decided_at=int(self.clock.now().timestamp()),
        )
        self.unit.run(ADD_TICKET_DECISION, params)

    def decisions(self, ticket_id: int) -> tuple[TicketDecision, ...]:
        params = TicketDecisionsParams(ticket_id=ticket_id)
        return tuple(decision_of(row) for row in self.unit.all(TICKET_DECISIONS, params))
