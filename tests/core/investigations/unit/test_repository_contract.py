"""The investigation repository contract against the fake."""

from mightymodels_core.investigations import InvestigationRepository

from tests.core.investigations.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from tests.core.investigations.investigation_repository_suite import (
    InvestigationRepositoryContract,
)


class TestFakeInvestigationRepository(InvestigationRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        fake = FakeInvestigationRepository(ledger=InvestigationLedger())

        assert isinstance(fake, InvestigationRepository)
