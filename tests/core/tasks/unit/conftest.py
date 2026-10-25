"""The task and attempt repositories over the fakes."""

import pytest

from tests.core.tasks.fakes import FakeAttemptRepository, FakeTaskRepository, TaskLedger
from tests.core.tasks.repository_builders import FAKE_TICKET_IDS, TaskHarness


@pytest.fixture
def harness() -> TaskHarness:
    ledger = TaskLedger()
    ticket_id, other_ticket_id = FAKE_TICKET_IDS
    return TaskHarness(
        tasks=FakeTaskRepository(ledger=ledger),
        attempts=FakeAttemptRepository(ledger=ledger),
        ticket_id=ticket_id,
        other_ticket_id=other_ticket_id,
    )
