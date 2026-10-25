"""The investigation repository over the fake."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.core.investigations.investigation_builders import InvestigationHarness


@pytest.fixture
def harness(fake_harness: InvestigationHarness) -> InvestigationHarness:
    return fake_harness
