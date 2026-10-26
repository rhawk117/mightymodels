"""What a hook reads of the ticket whose branch is checked out: its started and blocked tasks.

The ticket is the one ticket of this repository, not closed, whose branch is the checked-out
branch. A detached HEAD, no match and more than one match mean no ticket, and the hook does
nothing; `BranchTickets.unclosed` names every match, so a hook can tell no ticket from several.
With no ticket directory near the working directory nothing is opened and nothing is read. A
repository the database has not recorded holds no ticket. Any other failure to read is returned
as the error, so the caller can tell none from unreadable.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.database import DatabaseError
from mightymodels_core.edge import open_state
from mightymodels_core.primitives import StateError
from mightymodels_core.tasks import SqliteAttemptRepository, SqliteTaskRepository
from mightymodels_core.tasks.gates import STUCK
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import UnknownRepositoryError, read_entry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import TaskId
    from mightymodels_core.tasks import TaskRecord
    from mightymodels_core.units_of_work import Entry
    from mightymodels_core.vocabulary.tasks import TaskStatus, Worker

    from mightymodels_hooks.hook_context import HookContext

STATE_UNREADABLE = (StateError, DatabaseError, OSError)
IN_PROGRESS: frozenset[TaskStatus] = frozenset({'in-progress'})


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedTask:
    id: str
    owned: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class BlockedTask:
    id: str
    status: str
    reasons: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchTickets:
    unclosed: tuple[str, ...] = ()
    in_progress: tuple[str, ...] = ()
    auto_escalate: bool = False
    blocked: tuple[BlockedTask, ...] = ()


type StartedOrUnreadable = tuple[StartedTask, ...] | Exception
type BranchTicketsOrUnreadable = BranchTickets | Exception


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketReads:
    tasks: SqliteTaskRepository
    attempts: SqliteAttemptRepository
    ticket_id: int

    def started_by(self, worker: Worker) -> tuple[StartedTask, ...]:
        owned = {record.key: record.owned for record in self.tasks.tasks(self.ticket_id)}
        keys = self.tasks.in_progress_started_by(self.ticket_id, worker)
        return tuple(StartedTask(id=key, owned=owned[key]) for key in keys)

    def escalated(self) -> set[TaskId]:
        starts = self.attempts.latest_transition_of_each_task_into(self.ticket_id, IN_PROGRESS)
        started = self.tasks.in_progress_started_by(self.ticket_id, 'architect')
        return {key for key in started if starts[key].before in STUCK}

    def blocked(self, records: Sequence[TaskRecord]) -> tuple[BlockedTask, ...]:
        blocks = self.attempts.latest_transition_of_each_task_into(self.ticket_id, STUCK)
        escalated = self.escalated()
        return tuple(
            BlockedTask(
                id=record.key,
                status=blocks[record.key].after,
                reasons=tuple(map(str, blocks[record.key].reasons)),
            )
            for record in records
            if record.status in STUCK or record.key in escalated
        )


def ticket_reads_of(entry: Entry, ticket_id: int) -> TicketReads:
    return TicketReads(
        tasks=SqliteTaskRepository(unit=entry.unit),
        attempts=SqliteAttemptRepository(unit=entry.unit),
        ticket_id=ticket_id,
    )


def started_on_branch(entry: Entry, branch: str | None, worker: Worker) -> tuple[StartedTask, ...]:
    tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
    slug = None if branch is None else tickets.unclosed_on_branch(branch)
    if slug is None:
        return ()

    return ticket_reads_of(entry, tickets.staged_ticket(slug).id).started_by(worker)


def tickets_on_branch(entry: Entry, branch: str | None) -> BranchTickets:
    tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
    unclosed = [] if branch is None else tickets.all_unclosed_on_branch(branch)
    names = tuple(map(str, unclosed))
    if len(unclosed) != 1:
        return BranchTickets(unclosed=names)

    ticket = tickets.staged_ticket(unclosed[0])
    reads = ticket_reads_of(entry, ticket.id)
    records = reads.tasks.tasks(ticket.id)
    return BranchTickets(
        unclosed=names,
        in_progress=tuple(record.key for record in records if record.status == 'in-progress'),
        auto_escalate=ticket.section.auto_escalate,
        blocked=reads.blocked(records),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchState:
    context: HookContext

    async def read_started(self, worker: Worker) -> tuple[StartedTask, ...]:
        async with open_state(self.context.data_directory(), self.context.start()) as state:
            branch = await state.git.current_branch()
            with read_entry(state.database, state.checkout.repository_key()) as entry:
                return started_on_branch(entry, branch, worker)

    async def read_tickets(self) -> BranchTickets:
        async with open_state(self.context.data_directory(), self.context.start()) as state:
            branch = await state.git.current_branch()
            with read_entry(state.database, state.checkout.repository_key()) as entry:
                return tickets_on_branch(entry, branch)

    async def started_by(self, worker: Worker) -> StartedOrUnreadable:
        if not self.context.has_ticket_directory():
            return ()

        try:
            return await self.read_started(worker)
        except UnknownRepositoryError:
            return ()
        except STATE_UNREADABLE as error:
            return error

    async def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        if not self.context.has_ticket_directory():
            return BranchTickets()

        try:
            return await self.read_tickets()
        except UnknownRepositoryError:
            return BranchTickets()
        except STATE_UNREADABLE as error:
            return error
