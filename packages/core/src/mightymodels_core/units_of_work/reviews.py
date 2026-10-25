"""The review unit of work: one unit per tool call, the stores and services on it."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.reviews import (
    ReviewDecisionService,
    ReviewService,
    SqliteReviewDecisionRepository,
    SqliteReviewRepository,
)
from mightymodels_core.similarity import SqliteSimilarityRepository

from .entry import read_entry, write_entry

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RepositoryKey

    from .entry import Entry


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewUnit:
    reviews: ReviewService
    decisions: ReviewDecisionService


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewWork:
    database: Database
    repository_key: RepositoryKey
    clock: Clock

    @contextmanager
    def read(self) -> Generator[ReviewUnit]:
        with read_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    @contextmanager
    def write(self) -> Generator[ReviewUnit]:
        with write_entry(self.database, self.repository_key) as entry:
            yield self.create_unit(entry)

    def create_unit(self, entry: Entry) -> ReviewUnit:
        unit = entry.unit
        repository_id = entry.repository_id
        runs = SqliteReviewRepository(unit=unit, repository_id=repository_id)
        decisions = SqliteReviewDecisionRepository(unit=unit, repository_id=repository_id)
        reviews = ReviewService(
            reviews=runs,
            decisions=decisions,
            similarity=SqliteSimilarityRepository(unit=unit, repository_id=repository_id),
            clock=self.clock,
        )
        decision_service = ReviewDecisionService(
            reviews=runs, decisions=decisions, clock=self.clock
        )
        return ReviewUnit(reviews=reviews, decisions=decision_service)
