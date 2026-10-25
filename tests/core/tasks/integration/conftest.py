"""The task and attempt repositories over a real sqlite unit."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.tasks import SqliteAttemptRepository, SqliteTaskRepository

from tests.core.tasks.repository_builders import TaskHarness

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database


@pytest.fixture
def harness(database: Database, staged_ticket_ids: tuple[int, int]) -> Generator[TaskHarness]:
    ticket_id, other_ticket_id = staged_ticket_ids
    with database.write() as unit:
        yield TaskHarness(
            tasks=SqliteTaskRepository(unit=unit),
            attempts=SqliteAttemptRepository(unit=unit),
            ticket_id=ticket_id,
            other_ticket_id=other_ticket_id,
        )
