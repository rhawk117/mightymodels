"""The similarity repositories over a real sqlite unit."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.similarity import SqliteScoutReportRepository, SqliteSimilarityRepository

from tests.core.similarity.similarity_builders import SimilarityHarness

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database


@pytest.fixture
def harness(database: Database) -> Generator[SimilarityHarness]:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        yield SimilarityHarness(
            similarity=SqliteSimilarityRepository(unit=unit, repository_id=repository.id),
            scouts=SqliteScoutReportRepository(unit=unit, repository_id=repository.id),
        )
