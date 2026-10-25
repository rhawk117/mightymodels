"""The similarity repository contract against the fake."""

from mightymodels_core.similarity import SimilarityRepository

from tests.core.similarity.fakes import FakeSimilarityRepository
from tests.core.similarity.similarity_repository_suite import SimilarityRepositoryContract


class TestFakeSimilarityRepository(SimilarityRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeSimilarityRepository(), SimilarityRepository)
