"""The ticket repository contract against the fake."""

from mightymodels_core.tickets import TicketRepository

from tests.core.tickets.fakes import FakeTicketRepository
from tests.core.tickets.ticket_repository_suite import TicketRepositoryContract


class TestFakeTicketRepository(TicketRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeTicketRepository(), TicketRepository)
