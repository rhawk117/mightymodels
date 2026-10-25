"""The journal unit of work: crashouts, similarity and scout reports, scoped to the repository."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.crashouts import CrashoutService, SqliteCrashoutRepository
from mightymodels_core.similarity import (
    SimilarityService,
    SqliteScoutReportRepository,
    SqliteSimilarityRepository,
)

from .entry import read_entry, write_entry

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RepositoryKey

    from .entry import Entry


@dataclass(slots=True, kw_only=True, frozen=True)
class JournalUnit:
    crashouts: CrashoutService
    similarity: SimilarityService


@dataclass(slots=True, kw_only=True, frozen=True)
class JournalWork:
    database: Database
    repository_key: RepositoryKey
    clock: Clock

    @contextmanager
    def read(self) -> Generator[JournalUnit]:
        with read_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    @contextmanager
    def write(self) -> Generator[JournalUnit]:
        with write_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    def create_unit(self, entry: Entry) -> JournalUnit:
        unit = entry.unit
        repository_id = entry.repository_id
        similarity = SqliteSimilarityRepository(unit=unit, repository_id=repository_id)
        crashouts = CrashoutService(
            crashouts=SqliteCrashoutRepository(unit=unit, repository_id=repository_id),
            similarity=similarity,
            clock=self.clock,
        )
        scouts = SqliteScoutReportRepository(unit=unit, repository_id=repository_id)
        return JournalUnit(
            crashouts=crashouts, similarity=SimilarityService(similarity=similarity, scouts=scouts)
        )
