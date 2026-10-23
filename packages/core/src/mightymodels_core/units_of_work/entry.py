"""The entry every unit of work opens: one Unit and the repository id, resolved once."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.reviews import (
    ReviewDecisionService,
    SqliteReviewDecisionRepository,
    SqliteReviewRepository,
)
from mightymodels_core.schemas.repositories import (
    ENSURE_REPOSITORY,
    REPOSITORY_BY_KEY,
    RepositoryKeyParams,
)

from .errors import UnknownRepositoryError

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database, Unit
    from mightymodels_core.primitives import Clock, RepositoryKey


@dataclass(slots=True, kw_only=True, frozen=True)
class Entry:
    unit: Unit
    repository_id: int


@contextmanager
def read_entry(database: Database, repository_key: RepositoryKey) -> Generator[Entry]:
    with database.read() as unit:
        row = unit.one(REPOSITORY_BY_KEY, RepositoryKeyParams(repository_key=repository_key))
        if row is None:
            raise UnknownRepositoryError(repository_key=repository_key)

        yield Entry(unit=unit, repository_id=row.id)


@contextmanager
def write_entry(database: Database, repository_key: RepositoryKey) -> Generator[Entry]:
    with database.write() as unit:
        row = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key=repository_key))
        if row is None:
            raise UnknownRepositoryError(repository_key=repository_key)

        yield Entry(unit=unit, repository_id=row.id)


def review_decisions_of(entry: Entry, clock: Clock) -> ReviewDecisionService:
    return ReviewDecisionService(
        reviews=SqliteReviewRepository(unit=entry.unit, repository_id=entry.repository_id),
        decisions=SqliteReviewDecisionRepository(
            unit=entry.unit, repository_id=entry.repository_id
        ),
        clock=clock,
    )
