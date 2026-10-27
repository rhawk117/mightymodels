"""The snapshot service: a ticket's objective state, read from the stores and the git facts.

A snapshot is what a handoff needs and nothing a model wrote from memory: the ticket, the
repository, every task with its attempts, each contract command judged at HEAD from its latest
receipt, the passing commands, the failed and blocked attempts not to repeat, and where the latest
review run stands. Each list is cut to the caller's limit. The decisions and the open questions are
the live entries of the investigations the ticket links, and a linked investigation with no ledger
is a warning.

It takes values and returns values. The caller asks git first and passes the answer in, wraps a
call in its unit of work, renders the record and writes the files; the service never touches git,
a process or the filesystem.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.investigations.ledger import linked_ledgers
from mightymodels_core.snapshot.records import DEFAULT_LIMIT, SnapshotRecord
from mightymodels_core.snapshot.sections import (
    check_states,
    decision_lines,
    failed_attempts,
    git_warnings,
    ledger_lines,
    ledger_warnings,
    passing_commands,
    repository_state,
    review_state,
    task_state,
    ticket_summary,
)
from mightymodels_core.tasks.gates import STUCK

if TYPE_CHECKING:
    from mightymodels_core.contract.repository import ContractRepository
    from mightymodels_core.investigations.repository import InvestigationRepository
    from mightymodels_core.primitives import Clock, Slug
    from mightymodels_core.reviews.services import ReviewDecisionService
    from mightymodels_core.snapshot.records import RepositoryFacts
    from mightymodels_core.tasks.repository import AttemptRepository, TaskRepository
    from mightymodels_core.ticket_decisions import TicketDecisionRepository
    from mightymodels_core.tickets.repository import TicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotRequest:
    slug: Slug
    repository: RepositoryFacts
    limit: int = DEFAULT_LIMIT


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotService:
    tickets: TicketRepository
    tasks: TaskRepository
    attempts: AttemptRepository
    contracts: ContractRepository
    investigations: InvestigationRepository
    reviews: ReviewDecisionService
    ticket_decisions: TicketDecisionRepository
    clock: Clock

    def take(self, request: SnapshotRequest) -> SnapshotRecord:
        ticket = self.tickets.staged_ticket(request.slug)
        limit = request.limit
        repository = repository_state(request.repository, limit)
        commands = self.contracts.commands(ticket.id)
        receipts = self.contracts.latest_receipts(ticket.id)
        linked = linked_ledgers(self.investigations, ticket.investigations)
        attempts = self.attempts.attempts_by_worker(ticket.id)
        stuck = self.attempts.latest_transitions_into(ticket.id, STUCK, limit)
        return SnapshotRecord(
            slug=request.slug,
            generated_at=self.clock.now(),
            ticket=ticket_summary(ticket),
            repository=repository,
            tasks=tuple(task_state(task, attempts) for task in self.tasks.tasks(ticket.id)),
            checks=check_states(commands, receipts, repository.head),
            works=passing_commands(commands, receipts, limit),
            decisions=decision_lines(
                linked.ledgers, self.ticket_decisions.decisions(ticket.id), limit
            ),
            open_questions=ledger_lines(linked.ledgers, 'open', limit),
            do_not_retry=failed_attempts(stuck),
            review=review_state(self.reviews.latest_review(request.slug), limit),
            warnings=(*git_warnings(request.repository.refusal), *ledger_warnings(linked)),
        )
