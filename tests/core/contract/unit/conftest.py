"""The contract repository over the fake."""

import pytest

from tests.core.contract.contract_builders import FAKE_TICKET_IDS, ContractHarness
from tests.core.contract.fakes import ContractLedger, FakeContractRepository


@pytest.fixture
def harness() -> ContractHarness:
    ticket_id, other_ticket_id = FAKE_TICKET_IDS
    return ContractHarness(
        contract=FakeContractRepository(ledger=ContractLedger()),
        ticket_id=ticket_id,
        other_ticket_id=other_ticket_id,
    )
