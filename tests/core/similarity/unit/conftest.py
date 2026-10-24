"""The similarity repositories over the fakes."""

import pytest

from tests.core.similarity.fakes import FakeScoutReportRepository, FakeSimilarityRepository
from tests.core.similarity.similarity_builders import SimilarityHarness


@pytest.fixture
def harness() -> SimilarityHarness:
    return SimilarityHarness(
        similarity=FakeSimilarityRepository(), scouts=FakeScoutReportRepository()
    )
