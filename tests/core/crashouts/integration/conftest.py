"""The crashout repository over a real sqlite unit."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.crashouts import SqliteCrashoutRepository
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams

from tests.core.crashouts.crashout_builders import CrashoutHarness

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database


@pytest.fixture
def harness(database: Database) -> Generator[CrashoutHarness]:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        yield CrashoutHarness(
            crashouts=SqliteCrashoutRepository(unit=unit, repository_id=repository.id)
        )
