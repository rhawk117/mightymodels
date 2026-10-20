from typing import TYPE_CHECKING

import pytest
from mightymodels_core.investigations import InvestigationRecord
from mightymodels_core.primitives import Slug, redact

if TYPE_CHECKING:
    from mightymodels_core.units_of_work import TicketWork


class UnitFailedError(Exception):
    pass


def fail_after_writes(ticket_work: TicketWork, slug: Slug) -> None:
    investigation = InvestigationRecord(
        key=Slug('first-look'), target=redact('target'), kind='behavior'
    )
    with ticket_work.write() as unit:
        unit.tickets.investigations.add_investigation(investigation)
        unit.tickets.stage(slug, unit.files.source(slug))
        raise UnitFailedError


@pytest.fixture
def text_before_failure(ticket_work: TicketWork, slug: Slug, written_text: str) -> str:
    with pytest.raises(UnitFailedError):
        fail_after_writes(ticket_work, slug)
    return written_text


@pytest.mark.integration
class TestWriteUnitRollback:
    @pytest.mark.usefixtures('text_before_failure')
    def test_error_in_a_write_unit_rolls_back_every_repositorys_writes(
        self, ticket_work: TicketWork, slug: Slug
    ) -> None:
        with ticket_work.write() as unit:
            assert unit.tickets.tickets.ticket(slug) is None
            assert unit.tickets.investigations.investigation(Slug('first-look')) is None

    def test_error_in_a_write_unit_leaves_the_stored_file_in_place(
        self, ticket_work: TicketWork, slug: Slug, text_before_failure: str
    ) -> None:
        with ticket_work.read() as unit:
            assert unit.files.source(slug).text == text_before_failure
