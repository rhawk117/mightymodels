"""The review decision repository contract against the fake."""

from mightymodels_core.reviews import ReviewDecisionRepository

from tests.core.reviews.decision_repository_suite import DecisionRepositoryContract
from tests.core.reviews.fakes import FakeReviewDecisionRepository, ReviewLedger


class TestFakeReviewDecisionRepository(DecisionRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(
            FakeReviewDecisionRepository(ledger=ReviewLedger()), ReviewDecisionRepository
        )
