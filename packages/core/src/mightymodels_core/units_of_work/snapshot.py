"""The snapshot unit of work: one read unit per tool call, the stores and service on it."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.contract import SqliteContractRepository
from mightymodels_core.investigations import SqliteInvestigationRepository
from mightymodels_core.reviews import (
    ReviewDecisionService,
    SqliteReviewDecisionRepository,
    SqliteReviewRepository,
)
from mightymodels_core.snapshot import SnapshotService
from mightymodels_core.tasks import SqliteAttemptRepository, SqliteTaskRepository
from mightymodels_core.tickets import SqliteTicketRepository

from .entry import read_entry

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RepositoryKey

    from .entry import Entry


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotUnit:
    snapshots: SnapshotService


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotRead:
    database: Database
    repository_key: RepositoryKey
    clock: Clock

    @contextmanager
    def read(self) -> Generator[SnapshotUnit]:
        with read_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    def create_unit(self, entry: Entry) -> SnapshotUnit:
        unit = entry.unit
        repository_id = entry.repository_id
        reviews = ReviewDecisionService(
            reviews=SqliteReviewRepository(unit=unit, repository_id=repository_id),
            decisions=SqliteReviewDecisionRepository(unit=unit, repository_id=repository_id),
            clock=self.clock,
        )
        snapshots = SnapshotService(
            tickets=SqliteTicketRepository(unit=unit, repository_id=repository_id),
            tasks=SqliteTaskRepository(unit=unit),
            attempts=SqliteAttemptRepository(unit=unit),
            contracts=SqliteContractRepository(unit=unit),
            investigations=SqliteInvestigationRepository(unit=unit, repository_id=repository_id),
            reviews=reviews,
            clock=self.clock,
        )
        return SnapshotUnit(snapshots=snapshots)
