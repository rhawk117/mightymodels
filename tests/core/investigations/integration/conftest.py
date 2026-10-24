"""The investigation repository over a real sqlite unit."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.investigations import SqliteInvestigationRepository

from tests.core.investigations.investigation_builders import InvestigationHarness

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database


@pytest.fixture
def harness(database: Database, repository_id: int) -> Generator[InvestigationHarness]:
    with database.write() as unit:
        yield InvestigationHarness(
            investigations=SqliteInvestigationRepository(unit=unit, repository_id=repository_id)
        )
