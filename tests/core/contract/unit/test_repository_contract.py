"""The contract repository contract against the fake."""

from mightymodels_core.contract import ContractRepository

from tests.core.contract.contract_repository_suite import ContractRepositoryContract
from tests.core.contract.fakes import ContractLedger, FakeContractRepository


class TestFakeContractRepository(ContractRepositoryContract):
    pass


class TestFakeImplementation:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeContractRepository(ledger=ContractLedger()), ContractRepository)
