"""A ticket repository kept in memory, with the investigations that have a record."""

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from mightymodels_core.tickets.errors import (
    NotStagedError,
    UnknownInvestigationError,
)
from mightymodels_core.tickets.records import TicketRecord

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from mightymodels_core.primitives import Slug
    from mightymodels_core.schemas.tickets import TicketStatus
    from mightymodels_core.tickets.records import TicketSection


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeTicketRepository:
    recorded_investigations: Collection[str] = ()
    records: dict[Slug, TicketRecord] = field(default_factory=dict)

    def ticket(self, slug: Slug) -> TicketRecord | None:
        return self.records.get(slug)

    def staged_ticket(self, slug: Slug) -> TicketRecord:
        record = self.ticket(slug)
        if record is None:
            raise NotStagedError(slug=slug)
        return record

    def stage(self, slug: Slug, section: TicketSection, declared: Sequence[str]) -> TicketRecord:
        for key in declared:
            if key not in self.recorded_investigations:
                raise UnknownInvestigationError(slug=slug, investigation_key=key)

        existing = self.ticket(slug)
        previous = () if existing is None else existing.investigations
        ticket_id = len(self.records) + 1 if existing is None else existing.id
        record = TicketRecord(
            id=ticket_id,
            slug=slug,
            status='staged' if existing is None else existing.status,
            section=section,
            investigations=(
                *previous,
                *(key for key in dict.fromkeys(declared) if key not in previous),
            ),
        )
        self.records[slug] = record
        return record

    def mark_in_progress(self, slug: Slug) -> None:
        self._set_status(self.staged_ticket(slug), 'in-progress')

    def mark_closed(self, slug: Slug) -> None:
        self._set_status(self.staged_ticket(slug), 'closed')

    def seed_status(self, slug: Slug, status: TicketStatus) -> None:
        self._set_status(self.staged_ticket(slug), status)

    def unclosed_on_branch(self, branch: str) -> Slug | None:
        on_branch = self.all_unclosed_on_branch(branch)
        return on_branch[0] if len(on_branch) == 1 else None

    def all_unclosed_on_branch(self, branch: str) -> list[Slug]:
        return sorted(
            record.slug
            for record in self.records.values()
            if record.section.branch == branch and record.status != 'closed'
        )

    def _set_status(self, record: TicketRecord, status: TicketStatus) -> None:
        self.records[record.slug] = replace(record, status=status)
