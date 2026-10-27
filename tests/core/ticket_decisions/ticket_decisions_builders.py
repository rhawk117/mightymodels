"""The fixed clock and staged decisions the ticket decision tests share."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from mightymodels_core.ticket_decisions import (
        IncomingDecision,
        SqliteTicketDecisionRepository,
        TicketDecision,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class FixedClock:
    moment: datetime

    def now(self) -> datetime:
        return self.moment


@dataclass(slots=True, kw_only=True, frozen=True)
class StagedDecisions:
    repository: SqliteTicketDecisionRepository
    ticket_id: int

    def add(self, decision: IncomingDecision) -> None:
        self.repository.add(self.ticket_id, decision)

    def decisions(self) -> tuple[TicketDecision, ...]:
        return self.repository.decisions(self.ticket_id)


type DecisionsFor = Callable[[str], StagedDecisions]
