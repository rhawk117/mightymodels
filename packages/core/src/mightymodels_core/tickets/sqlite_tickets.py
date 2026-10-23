"""The ticket repository over a core unit, working within one repository id."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import Slug, redact
from mightymodels_core.schemas.investigations import INVESTIGATION_BY_KEY, InvestigationKeyParams
from mightymodels_core.schemas.tickets import (
    LINK_TICKET_INVESTIGATION,
    SET_TICKET_STATUS,
    STAGE_TICKET,
    TICKET_BY_SLUG,
    UNCLOSED_SLUG_PAIR_ON_BRANCH,
    UNCLOSED_SLUGS_ON_BRANCH,
    BranchParams,
    LinkTicketInvestigationParams,
    SetTicketStatusParams,
    StageTicketParams,
    TicketSlugParams,
)
from mightymodels_core.tickets.errors import (
    NotStagedError,
    UnknownInvestigationError,
)
from mightymodels_core.tickets.records import TicketRecord, TicketSection, Tracker

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.database import Unit
    from mightymodels_core.schemas.tickets import TicketRow, TicketStatus
    from mightymodels_core.tickets.policy import OpenTicket


def record_of(row: TicketRow) -> TicketRecord:
    section = TicketSection(
        ticket=row.ticket,
        summary=redact(row.summary),
        branch=row.branch,
        scope=row.scope,
        plan_first=row.plan_first,
        auto_escalate=row.auto_escalate,
        models=row.models,
        tracker=Tracker(issue=row.issue, jira=row.jira),
        context=tuple(row.context),
        validated_at=row.validated_at,
    )
    return TicketRecord(
        id=row.id,
        slug=Slug(row.slug),
        status=row.status,
        section=section,
        investigations=tuple(row.investigations),
    )


def stage_params_of(repository_id: int, slug: Slug, section: TicketSection) -> StageTicketParams:
    return StageTicketParams(
        repository_id=repository_id,
        slug=slug,
        ticket=section.ticket,
        summary=section.summary,
        branch=section.branch,
        scope=section.scope,
        plan_first=section.plan_first,
        auto_escalate=section.auto_escalate,
        issue=section.tracker.issue,
        jira=section.tracker.jira,
        models=section.models,
        context=list(section.context),
        validated_at=section.validated_at,
    )


def row_of(unit: Unit, repository_id: int, slug: Slug) -> TicketRow | None:
    return unit.one(TICKET_BY_SLUG, TicketSlugParams(repository_id=repository_id, slug=slug))


def staged_row(unit: Unit, repository_id: int, slug: Slug) -> TicketRow:
    row = row_of(unit, repository_id, slug)
    if row is None:
        raise NotStagedError(slug=slug)
    return row


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteTicketRepository:
    unit: Unit
    repository_id: int

    def ticket(self, slug: Slug) -> TicketRecord | None:
        row = row_of(self.unit, self.repository_id, slug)
        return None if row is None else record_of(row)

    def staged_ticket(self, slug: Slug) -> TicketRecord:
        return record_of(staged_row(self.unit, self.repository_id, slug))

    def stage(self, slug: Slug, section: TicketSection, declared: Sequence[str]) -> TicketRecord:
        investigation_ids = [self.investigation_id(slug, key) for key in dict.fromkeys(declared)]
        self.unit.one(STAGE_TICKET, stage_params_of(self.repository_id, slug, section))
        ticket_id = staged_row(self.unit, self.repository_id, slug).id
        links = [
            LinkTicketInvestigationParams(ticket_id=ticket_id, investigation_id=investigation_id)
            for investigation_id in investigation_ids
        ]
        self.unit.run_many(LINK_TICKET_INVESTIGATION, links)
        return self.staged_ticket(slug)

    def mark_in_progress(self, ticket: OpenTicket) -> None:
        self.set_status(ticket.slug, 'in-progress')

    def mark_closed(self, ticket: OpenTicket) -> None:
        self.set_status(ticket.slug, 'closed')

    def unclosed_on_branch(self, branch: str) -> Slug | None:
        pair = self.unit.all(
            UNCLOSED_SLUG_PAIR_ON_BRANCH,
            BranchParams(repository_id=self.repository_id, branch=branch),
        )
        return Slug(pair[0].slug) if len(pair) == 1 else None

    def all_unclosed_on_branch(self, branch: str) -> list[Slug]:
        rows = self.unit.all(
            UNCLOSED_SLUGS_ON_BRANCH, BranchParams(repository_id=self.repository_id, branch=branch)
        )
        return [Slug(row.slug) for row in rows]

    def investigation_id(self, slug: Slug, investigation_key: str) -> int:
        row = self.unit.one(
            INVESTIGATION_BY_KEY,
            InvestigationKeyParams(
                repository_id=self.repository_id, investigation_key=investigation_key
            ),
        )
        if row is None:
            raise UnknownInvestigationError(slug=slug, investigation_key=investigation_key)
        return row.id

    def set_status(self, slug: Slug, status: TicketStatus) -> None:
        self.unit.run(
            SET_TICKET_STATUS,
            SetTicketStatusParams(repository_id=self.repository_id, slug=slug, status=status),
        )
