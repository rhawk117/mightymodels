"""The fixed clock and staged decisions the ticket decision tests share."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import STAGE_TICKET, StageTicketParams
from mightymodels_core.ticket_decisions import SqliteTicketDecisionRepository

if TYPE_CHECKING:
    from collections.abc import Callable

    from mightymodels_core.database import Unit
    from mightymodels_core.ticket_decisions import IncomingDecision, TicketDecision

DATABASE_FILE = 'mightymodels.db'
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


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


def stage_decisions(unit: Unit, slug: str) -> StagedDecisions:
    repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
    assert repository is not None
    params = StageTicketParams(
        repository_id=repository.id,
        slug=slug,
        ticket=f'ticket {slug}',
        summary='summary',
        branch='main',
        scope='med',
        plan_first=False,
        auto_escalate=False,
        issue=None,
        jira=None,
        models={},
        context=[],
        validated_at=NOW,
    )
    staged = unit.one(STAGE_TICKET, params)
    assert staged is not None
    repository_of_decisions = SqliteTicketDecisionRepository(
        unit=unit, clock=FixedClock(moment=NOW)
    )
    return StagedDecisions(repository=repository_of_decisions, ticket_id=staged.id)
