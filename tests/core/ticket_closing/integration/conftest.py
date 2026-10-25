"""The closing repository over a real sqlite unit."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.ticket_closing import SqliteClosingRepository

from tests.core.ticket_closing.closing_builders import ClosingHarness

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database


@pytest.fixture
def harness(database: Database, staged_ticket_id: int) -> Generator[ClosingHarness]:
    with database.write() as unit:
        yield ClosingHarness(
            repository=SqliteClosingRepository(unit=unit), ticket_id=staged_ticket_id
        )
