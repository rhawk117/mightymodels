"""The close service: what still blocks closing a ticket, and the closing itself.

It takes values and returns values. The caller asks git, looks for the debug note, picks the
archive path, wraps a call in its unit of work, writes the archive files and words the response;
the service never touches git or the filesystem. Live work is what a closed ticket would strand,
and `check` answers it as a value, for a closed ticket too. Close runs as two calls so the caller
can ask git between them: `prepare` reads the ticket, and `close` takes the facts, reads the
ticket again and refuses when its status, branch or investigations moved since. It then refuses
while live work remains, needs the shipped line and holds the gotcha limit, marks the ticket closed
and stores its closing.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.investigations.ledger import linked_ledgers
from mightymodels_core.ticket_closing.archive import ArchiveSources, create_archive_record
from mightymodels_core.ticket_closing.errors import LiveWorkRemainsError, TicketMovedError
from mightymodels_core.ticket_closing.policy import (
    ClosingOptions,
    ClosingPolicy,
    LiveWorkPolicy,
    create_one_lined_closing,
    get_moved_fields,
)
from mightymodels_core.ticket_closing.records import ClosingRecord
from mightymodels_core.tickets.policy import get_closed_problem

if TYPE_CHECKING:
    from mightymodels_core.contract.repository import ContractRepository
    from mightymodels_core.investigations.repository import InvestigationRepository
    from mightymodels_core.primitives import Clock, Slug
    from mightymodels_core.reviews.services import LatestReview, ReviewDecisionService
    from mightymodels_core.tasks.repository import AttemptRepository, TaskRepository
    from mightymodels_core.ticket_closing.archive import ArchiveRecord
    from mightymodels_core.ticket_closing.records import CloseFacts, ClosingLines, OneLinedClosing
    from mightymodels_core.ticket_closing.repository import ClosingRepository
    from mightymodels_core.tickets.records import TicketRecord
    from mightymodels_core.tickets.repository import TicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseRequest:
    seen: TicketRecord
    facts: CloseFacts
    lines: ClosingLines
    archive: str


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseCheck:
    blockers: tuple[str, ...]
    git_refusal: str | None

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)


@dataclass(slots=True, kw_only=True, frozen=True)
class ClosedTicket:
    closing: ClosingRecord
    archive: ArchiveRecord


@dataclass(slots=True, kw_only=True, frozen=True)
class ClosingService:
    tickets: TicketRepository
    tasks: TaskRepository
    attempts: AttemptRepository
    contracts: ContractRepository
    review_decisions: ReviewDecisionService
    investigations: InvestigationRepository
    closings: ClosingRepository
    clock: Clock
    options: ClosingOptions = field(default_factory=ClosingOptions)

    def prepare(self, slug: Slug) -> TicketRecord:
        return self.tickets.staged_ticket(slug)

    def check(self, slug: Slug, facts: CloseFacts) -> CloseCheck:
        ticket = self.tickets.staged_ticket(slug)
        blockers = self.live_work(ticket, facts, self.latest_review(slug))
        return CloseCheck(blockers=tuple(blockers), git_refusal=facts.git_refusal)

    def close(self, slug: Slug, request: CloseRequest) -> ClosedTicket:
        ticket = self.tickets.staged_ticket(slug)
        if problem := get_closed_problem(ticket):
            raise problem

        if moved := get_moved_fields(request.seen, ticket):
            raise TicketMovedError(slug=slug, changed=moved)

        review = self.latest_review(slug)
        if blockers := self.live_work(ticket, request.facts, review):
            raise LiveWorkRemainsError(
                slug=slug, blockers=blockers, git_refusal=request.facts.git_refusal
            )

        lines = create_one_lined_closing(request.lines, self.options)
        if problem := ClosingPolicy(closing=lines, options=self.options).get_closing_problem():
            raise problem

        closing = self.closing_record_of(request, lines)
        archive = create_archive_record(self.archive_sources(ticket, closing, review))
        self.tickets.mark_closed(slug)
        self.closings.record_closing(ticket.id, closing)
        return ClosedTicket(closing=closing, archive=archive)

    def closing_record_of(self, request: CloseRequest, lines: OneLinedClosing) -> ClosingRecord:
        return ClosingRecord(
            closed_at=self.clock.now(),
            head=request.facts.head,
            shipped=lines.shipped,
            pr=lines.pr,
            gotchas=lines.gotchas,
            archive=request.archive,
        )

    def latest_review(self, slug: Slug) -> LatestReview | None:
        return self.review_decisions.latest_review(slug)

    def live_work(
        self, ticket: TicketRecord, facts: CloseFacts, review: LatestReview | None
    ) -> list[str]:
        policy = LiveWorkPolicy(
            branch=ticket.section.branch,
            tasks=self.tasks.tasks(ticket.id),
            review=review,
            facts=facts,
        )
        return policy.get_live_work_blockers()

    def archive_sources(
        self, ticket: TicketRecord, closing: ClosingRecord, review: LatestReview | None
    ) -> ArchiveSources:
        return ArchiveSources(
            ticket=ticket,
            closing=closing,
            tasks=self.tasks.tasks(ticket.id),
            attempts=self.attempts.attempts_by_worker(ticket.id),
            commands=self.contracts.commands(ticket.id),
            receipts=self.contracts.latest_receipts(ticket.id),
            ledgers=linked_ledgers(self.investigations, ticket.investigations).ledgers,
            review=review,
            decision_limit=self.options.decision_limit,
        )
