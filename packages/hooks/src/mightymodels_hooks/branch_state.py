"""What a hook reads of the ticket whose branch is checked out: its started and blocked tasks.

The ticket is the one ticket of this repository, not closed, whose branch is the checked-out
branch. A detached HEAD, no match and more than one match mean no ticket, and the hook does
nothing; `BranchTickets.unclosed` names every match, so a hook can tell no ticket from several.
With no ticket directory near the working directory nothing is opened and nothing is read. A
repository the database has not recorded holds no ticket. Any other failure to read is returned
as the error, so the caller can tell none from unreadable.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mightymodels_core.contract import SqliteContractRepository
from mightymodels_core.tasks import SqliteAttemptRepository, SqliteTaskRepository, TaskReadService
from mightymodels_core.tasks.gates import STUCK, get_receipt_problem
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import UnknownRepositoryError

from mightymodels_hooks.hook_context import STATE_UNREADABLE

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.contract import Receipt, RecordedCommand
    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import TaskId
    from mightymodels_core.tasks import TaskRecord
    from mightymodels_core.tickets import TicketRecord
    from mightymodels_core.units_of_work import Entry
    from mightymodels_core.vocabulary.tasks import TaskStatus, Worker

    from mightymodels_hooks.hook_context import HookContext

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


@dataclass(slots=True, kw_only=True, frozen=True)
class Landing:
    unclosed: tuple[str, ...] = ()
    unproven: tuple[str, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchTicket:
    unclosed: tuple[str, ...] = ()
    ticket: TicketRecord | None = None


type StartedOrUnreadable = tuple[StartedTask, ...] | Exception
type BranchTicketsOrUnreadable = BranchTickets | Exception
type LandingOrUnreadable = Landing | Exception


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
        auto_escalate=ticket.section.auto_escalate,
        blocked=reads.blocked(records),
    )


def not_proven_in_landing(
    commands: Sequence[RecordedCommand], receipts: Mapping[str, Receipt], head: str | None
) -> list[str]:
    passed_at_head = (
        receipts[command.key]
        for command in commands
        if get_receipt_problem(command.key, receipts.get(command.key), head) is None
    )
    return [
        f'{receipt.key} passed at HEAD in the {receipt.phase} phase, not the landing phase'
        for receipt in passed_at_head
        if receipt.phase != 'landing'
    ]


def live_commands(
    contracts: SqliteContractRepository, ticket_id: int, records: Sequence[TaskRecord]
) -> list[RecordedCommand]:
    superseded = {record.key for record in records if record.status == 'superseded'}
    return [
        command for command in contracts.commands(ticket_id) if command.task_key not in superseded
    ]


def landing_on_branch(entry: Entry, branch: str | None, head: str | None) -> Landing:
    found = branch_ticket(entry, branch)
    ticket = found.ticket
    if ticket is None:
        return Landing(unclosed=found.unclosed)

    tickets = tickets_of(entry)
    reads = ticket_reads_of(entry, ticket.id)
    contracts = SqliteContractRepository(unit=entry.unit)
    service = TaskReadService(
        tickets=tickets, tasks=reads.tasks, attempts=reads.attempts, contracts=contracts
    )
    readiness = service.ready(ticket.slug, head)
    live = live_commands(contracts, reads.ticket_id, readiness.records)
    receipts = contracts.latest_receipts(reads.ticket_id)
    unproven = (*readiness.problems, *not_proven_in_landing(live, receipts, head))
    return Landing(unclosed=found.unclosed, unproven=unproven)


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
class LandingRead:
    async def read(self, state: OpenState, branch: str | None, entry: Entry) -> Landing:
        return landing_on_branch(entry, branch, await state.git.resolve_head())


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

    async def landing_on_branch(self) -> LandingOrUnreadable:
        return await self.guarded(LandingRead(), Landing())
