"""The review repository contract against the fake."""

from mightymodels_core.reviews import ReviewRepository

from tests.core.reviews.fakes import FakeReviewRepository, ReviewLedger
from tests.core.reviews.review_repository_suite import ReviewRepositoryContract


class TestFakeReviewRepository(ReviewRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeReviewRepository(ledger=ReviewLedger()), ReviewRepository)
