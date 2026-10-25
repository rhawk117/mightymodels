"""The investigation repository over the fake."""

import pytest

from tests.core.investigations.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from tests.core.investigations.investigation_builders import InvestigationHarness


@pytest.fixture
def harness() -> InvestigationHarness:
    return InvestigationHarness(
        investigations=FakeInvestigationRepository(ledger=InvestigationLedger())
    )
