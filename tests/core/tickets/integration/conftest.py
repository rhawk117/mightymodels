"""The ticket repository over a real sqlite unit."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.tickets import SqliteTicketRepository

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database
    from mightymodels_core.tickets import TicketRepository


@pytest.fixture
def repository(database: Database, repository_id: int) -> Generator[TicketRepository]:
    with database.write() as unit:
        yield SqliteTicketRepository(unit=unit, repository_id=repository_id)
