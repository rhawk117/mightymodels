"""The ticket repository over the fake."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from mightymodels_core.tickets import TicketRepository


@pytest.fixture
def repository(fake_repository: TicketRepository) -> TicketRepository:
    return fake_repository
