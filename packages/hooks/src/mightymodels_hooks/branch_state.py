"""What a hook reads of the ticket whose branch is checked out: its started tasks.

The ticket is the one ticket of this repository, not closed, whose branch is the checked-out
branch. A detached HEAD, no match and more than one match mean no ticket, and the hook does
nothing; `BranchTickets.unclosed` names every match, so a hook can tell no ticket from several.
With no ticket directory near the working directory nothing is opened and nothing is read. A
repository the database has not recorded holds no ticket. Any other failure to read is returned
as the error, so the caller can tell none from unreadable.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mightymodels_core.tasks import SqliteTaskRepository
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import UnknownRepositoryError

from mightymodels_hooks.hook_context import STATE_UNREADABLE

if TYPE_CHECKING:
    from mightymodels_core.edge import OpenState
    from mightymodels_core.tickets import TicketRecord
    from mightymodels_core.units_of_work import Entry
    from mightymodels_core.vocabulary.tasks import Worker

    from mightymodels_hooks.hook_context import HookContext


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedTask:
    id: str
    owned: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchTickets:
    unclosed: tuple[str, ...] = ()
    in_progress: tuple[str, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchTicket:
    unclosed: tuple[str, ...] = ()
    ticket: TicketRecord | None = None


type StartedOrUnreadable = tuple[StartedTask, ...] | Exception
type BranchTicketsOrUnreadable = BranchTickets | Exception


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketReads:
    tasks: SqliteTaskRepository
    ticket_id: int

    def started_by(self, worker: Worker) -> tuple[StartedTask, ...]:
        owned = {record.key: record.owned for record in self.tasks.tasks(self.ticket_id)}
        keys = self.tasks.in_progress_started_by(self.ticket_id, worker)
        return tuple(StartedTask(id=key, owned=owned[key]) for key in keys)


def ticket_reads_of(entry: Entry, ticket_id: int) -> TicketReads:
    return TicketReads(
        tasks=SqliteTaskRepository(unit=entry.unit),
        ticket_id=ticket_id,
    )


def tickets_of(entry: Entry) -> SqliteTicketRepository:
    return SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)


def branch_ticket(entry: Entry, branch: str | None) -> BranchTicket:
    tickets = tickets_of(entry)
    unclosed = [] if branch is None else tickets.all_unclosed_on_branch(branch)
    names = tuple(map(str, unclosed))
    if len(unclosed) != 1:
        return BranchTicket(unclosed=names)

    return BranchTicket(unclosed=names, ticket=tickets.staged_ticket(unclosed[0]))


def started_on_branch(entry: Entry, branch: str | None, worker: Worker) -> tuple[StartedTask, ...]:
    ticket = branch_ticket(entry, branch).ticket
    if ticket is None:
        return ()

    return ticket_reads_of(entry, ticket.id).started_by(worker)


def tickets_on_branch(entry: Entry, branch: str | None) -> BranchTickets:
    found = branch_ticket(entry, branch)
    ticket = found.ticket
    names = found.unclosed
    if ticket is None:
        return BranchTickets(unclosed=names)

    reads = ticket_reads_of(entry, ticket.id)
    records = reads.tasks.tasks(ticket.id)
    return BranchTickets(
        unclosed=names,
        in_progress=tuple(record.key for record in records if record.status == 'in-progress'),
    )


@runtime_checkable
class BranchRead[T](Protocol):
    async def read(self, state: OpenState, branch: str | None, entry: Entry, /) -> T: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedRead:
    worker: Worker

    async def read(
        self, _state: OpenState, branch: str | None, entry: Entry
    ) -> tuple[StartedTask, ...]:
        return started_on_branch(entry, branch, self.worker)


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketsRead:
    async def read(self, _state: OpenState, branch: str | None, entry: Entry) -> BranchTickets:
        return tickets_on_branch(entry, branch)


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchState:
    context: HookContext

    async def guarded[T](self, work: BranchRead[T], empty: T) -> T | Exception:
        if not self.context.has_ticket_directory():
            return empty

        try:
            async with self.context.branch_entry() as (state, branch, entry):
                return await work.read(state, branch, entry)
        except UnknownRepositoryError:
            return empty
        except STATE_UNREADABLE as error:
            return error

    def ticket_directory_holds(self, file_path: str) -> bool:
        return self.context.ticket_directory_holds(file_path)

    async def started_by(self, worker: Worker) -> StartedOrUnreadable:
        return await self.guarded(StartedRead(worker=worker), ())

    async def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        return await self.guarded(TicketsRead(), BranchTickets())
