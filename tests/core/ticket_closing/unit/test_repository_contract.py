"""The closing repository contract against the fake."""

from mightymodels_core.ticket_closing import ClosingRepository

from tests.core.ticket_closing.closing_repository_suite import ClosingRepositoryContract
from tests.core.ticket_closing.fakes import FakeClosingRepository


class TestFakeClosingRepository(ClosingRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeClosingRepository(), ClosingRepository)
