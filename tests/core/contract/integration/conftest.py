"""The contract repository over a real sqlite unit."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import SqliteContractRepository

from tests.core.contract.contract_builders import ContractHarness

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database


@pytest.fixture
def harness(database: Database, staged_ticket_ids: tuple[int, int]) -> Generator[ContractHarness]:
    ticket_id, other_ticket_id = staged_ticket_ids
    with database.write() as unit:
        yield ContractHarness(
            contract=SqliteContractRepository(unit=unit),
            ticket_id=ticket_id,
            other_ticket_id=other_ticket_id,
        )
