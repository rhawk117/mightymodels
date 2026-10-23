"""The task read service: shows the tasks of a ticket and says whether they are ready to close."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.tasks.gates import get_readiness_problems, get_receipt_problems

if TYPE_CHECKING:
    from mightymodels_core.contract.repository import ContractRepository
    from mightymodels_core.primitives import Slug
    from mightymodels_core.tasks.records import AttemptCounts, TaskRecord
    from mightymodels_core.tasks.repository import AttemptRepository, TaskRepository
    from mightymodels_core.tickets.repository import TicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskListing:
    records: list[TaskRecord]
    attempts: AttemptCounts


@dataclass(slots=True, kw_only=True, frozen=True)
class Readiness:
    records: list[TaskRecord]
    problems: list[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskReadService:
    tickets: TicketRepository
    tasks: TaskRepository
    attempts: AttemptRepository
    contracts: ContractRepository

    def show(self, slug: Slug) -> TaskListing:
        ticket_id = self.tickets.staged_ticket(slug).id
        return TaskListing(
            records=self.tasks.tasks(ticket_id),
            attempts=self.attempts.attempts_by_worker(ticket_id),
        )

    def ready(self, slug: Slug, head: str | None) -> Readiness:
        ticket_id = self.tickets.staged_ticket(slug).id
        records = self.tasks.tasks(ticket_id)
        superseded = {record.key for record in records if record.status == 'superseded'}
        live = [
            command
            for command in self.contracts.commands(ticket_id)
            if command.task_key not in superseded
        ]
        receipts = self.contracts.latest_receipts(ticket_id)
        problems = [
            *get_readiness_problems(records),
            *get_receipt_problems(live, receipts, head),
        ]
        return Readiness(records=records, problems=problems)
