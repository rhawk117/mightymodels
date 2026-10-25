from typing import TYPE_CHECKING

import pytest
from mightymodels_core.tickets import TicketExistsError
from mightymodels_core.units_of_work import MissingTicketError

if TYPE_CHECKING:
    from mightymodels_core.primitives import Slug
    from mightymodels_core.tickets import TicketAnswers
    from mightymodels_core.units_of_work import TicketWork
    from mightymodels_core.workspace import Workspace


pytestmark = [pytest.mark.integration]


class TestTicketFiles:
    def test_slot_of_a_missing_file_is_free(self, ticket_work: TicketWork, slug: Slug) -> None:
        with ticket_work.write() as unit:
            slot = unit.files.slot(slug)

        assert slot.path == '.mightymodels/add-widget/ticket.yml'
        assert not slot.exists

    def test_missing_file_is_refused_naming_the_path(
        self, ticket_work: TicketWork, slug: Slug
    ) -> None:
        with pytest.raises(MissingTicketError) as refusal, ticket_work.write() as unit:
            unit.files.source(slug)

        assert refusal.value.path == '.mightymodels/add-widget/ticket.yml'
        assert '.mightymodels/add-widget/ticket.yml does not exist' in str(refusal.value)

    def test_written_text_is_read_back_whole(
        self, ticket_work: TicketWork, slug: Slug, written_text: str
    ) -> None:
        with ticket_work.read() as unit:
            source = unit.files.source(slug)

        assert source.text == written_text
        assert source.path == '.mightymodels/add-widget/ticket.yml'


@pytest.mark.usefixtures('written_text')
class TestTicketWriting:
    def test_slot_of_a_written_file_is_taken(self, ticket_work: TicketWork, slug: Slug) -> None:
        with ticket_work.read() as unit:
            assert unit.files.slot(slug).exists

    def test_store_leaves_no_draft_behind(self, workspace: Workspace, slug: Slug) -> None:
        assert not workspace.ticket_draft(slug).exists()

    def test_writing_over_a_taken_slot_is_refused(
        self,
        ticket_work: TicketWork,
        slug: Slug,
        answers: TicketAnswers,
    ) -> None:
        with pytest.raises(TicketExistsError), ticket_work.write() as unit:
            unit.tickets.write(slug, answers, unit.files.slot(slug))

    def test_staged_ticket_is_shown_by_a_later_read_unit(
        self, ticket_work: TicketWork, slug: Slug
    ) -> None:
        with ticket_work.write() as unit:
            unit.tickets.stage(slug, unit.files.source(slug))

        with ticket_work.read() as unit:
            record = unit.tickets.show(slug)

        assert record.slug == slug
        assert record.section.summary == 'add the widget'


class TestTicketServices:
    def test_updated_context_is_stored_and_staged(
        self, ticket_work: TicketWork, slug: Slug, written_text: str
    ) -> None:
        assert written_text
        with ticket_work.write() as unit:
            source = unit.files.source(slug)
            update = unit.tickets.update_context(slug, source, ['only line'])
            unit.store(slug, update.text)

        with ticket_work.read() as unit:
            assert unit.files.source(slug).text == update.text
            assert unit.tickets.show(slug).section.context == ('only line',)

    def test_closing_service_shares_the_ticket_store(
        self, ticket_work: TicketWork, slug: Slug, written_text: str
    ) -> None:
        assert written_text
        with ticket_work.write() as unit:
            staged = unit.tickets.stage(slug, unit.files.source(slug))

            assert unit.closing.prepare(slug) == staged
