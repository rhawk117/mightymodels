"""The closing repository over the fake."""

import pytest

from tests.core.ticket_closing.closing_builders import FAKE_TICKET_ID, ClosingHarness
from tests.core.ticket_closing.fakes import FakeClosingRepository


@pytest.fixture
def harness() -> ClosingHarness:
    return ClosingHarness(repository=FakeClosingRepository(), ticket_id=FAKE_TICKET_ID)
