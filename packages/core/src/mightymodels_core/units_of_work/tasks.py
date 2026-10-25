"""The task unit of work: one unit per tool call, the stores and services on it.

The task service and the contract service share the unit, so approving the contract runs in the
same transaction as the reads that precede it.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.contract import ContractService, SqliteContractRepository
from mightymodels_core.tasks import (
    SqliteAttemptRepository,
    SqliteTaskRepository,
    TaskReadService,
    TaskService,
)
from mightymodels_core.tickets import SqliteTicketRepository

from .entry import read_entry, write_entry

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RepositoryKey

    from .entry import Entry


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskUnit:
    tasks: TaskService
    task_reads: TaskReadService
    contracts: ContractService


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskWork:
    database: Database
    repository_key: RepositoryKey
    clock: Clock

    @contextmanager
    def read(self) -> Generator[TaskUnit]:
        with read_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    @contextmanager
    def write(self) -> Generator[TaskUnit]:
        with write_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    def create_unit(self, entry: Entry) -> TaskUnit:
        unit = entry.unit
        tickets = SqliteTicketRepository(unit=unit, repository_id=entry.repository_id)
        contracts = SqliteContractRepository(unit=unit)
        task_repository = SqliteTaskRepository(unit=unit)
        attempts = SqliteAttemptRepository(unit=unit)
        tasks = TaskService(
            tickets=tickets,
            tasks=task_repository,
            attempts=attempts,
            contracts=contracts,
            clock=self.clock,
        )
        task_reads = TaskReadService(
            tickets=tickets, tasks=task_repository, attempts=attempts, contracts=contracts
        )
        contract_service = ContractService(tickets=tickets, contracts=contracts, clock=self.clock)
        return TaskUnit(tasks=tasks, task_reads=task_reads, contracts=contract_service)
