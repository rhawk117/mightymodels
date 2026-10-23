"""The investigation unit of work: one unit per tool call, the stores and service on it."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.investigations import InvestigationService, SqliteInvestigationRepository
from mightymodels_core.similarity import SqliteSimilarityRepository

from .entry import read_entry, write_entry

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RepositoryKey

    from .entry import Entry


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationUnit:
    investigations: InvestigationService


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationWork:
    database: Database
    repository_key: RepositoryKey
    clock: Clock

    @contextmanager
    def read(self) -> Generator[InvestigationUnit]:
        with read_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    @contextmanager
    def write(self) -> Generator[InvestigationUnit]:
        with write_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    def create_unit(self, entry: Entry) -> InvestigationUnit:
        investigations = InvestigationService(
            investigations=SqliteInvestigationRepository(
                unit=entry.unit, repository_id=entry.repository_id
            ),
            similarity=SqliteSimilarityRepository(
                unit=entry.unit, repository_id=entry.repository_id
            ),
            clock=self.clock,
        )
        return InvestigationUnit(investigations=investigations)
