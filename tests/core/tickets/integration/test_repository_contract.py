"""Every ticket repository case runs against the sqlite store and the fake."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.tickets import (
    NotStagedError,
    TicketRepository,
    UnknownInvestigationError,
)
from mightymodels_core.tickets.policy import OpenTicket, open_ticket
from mightymodels_core.tickets.tests.fakes import FakeTicketRepository

from tests.core.tickets.conftest import RECORDED_INVESTIGATIONS, create_section

if TYPE_CHECKING:
    from collections.abc import Callable

    from mightymodels_core.tickets import TicketSection

FIRST = Slug('first')
SECOND = Slug('second')
THIRD = Slug('third')
FIRST_LOOK, SECOND_LOOK = RECORDED_INVESTIGATIONS
SECRET_SUMMARY = 'rotate sk-ant-' + 'a' * 24 + ' soon'


@pytest.fixture
def open_of(repository: TicketRepository) -> Callable[[Slug], OpenTicket]:
    def token(slug: Slug) -> OpenTicket:
        issued = open_ticket(repository.staged_ticket(slug))
        assert isinstance(issued, OpenTicket)
        return issued

    return token


class TestImplementations:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeTicketRepository(), TicketRepository)

    def test_repository_satisfies_the_protocol(self, repository: TicketRepository) -> None:
        assert isinstance(repository, TicketRepository)


class TestLookup:
    @pytest.fixture
    def staged(self, repository: TicketRepository) -> TicketRepository:
        repository.stage(FIRST, create_section(FIRST, 'main'), ())
        return repository

    def test_ticket_is_none_before_staging(self, repository: TicketRepository) -> None:
        assert repository.ticket(FIRST) is None

    def test_staged_ticket_is_found(self, staged: TicketRepository) -> None:
        record = staged.staged_ticket(FIRST)

        assert record.slug == FIRST
        assert record.status == 'staged'
        assert record.section == create_section(FIRST, 'main')
        assert record.investigations == ()

    def test_staged_ticket_refuses_an_unstaged_slug(self, repository: TicketRepository) -> None:
        with pytest.raises(NotStagedError):
            repository.staged_ticket(FIRST)

    def test_staged_ticket_still_finds_a_closed_ticket(
        self, staged: TicketRepository, open_of: Callable[[Slug], OpenTicket]
    ) -> None:
        staged.mark_closed(open_of(FIRST))

        assert staged.staged_ticket(FIRST).status == 'closed'


class TestStage:
    replacement: TicketSection = create_section(FIRST, 'feature')

    @pytest.fixture
    def linked(self, repository: TicketRepository) -> TicketRepository:
        repository.stage(FIRST, create_section(FIRST, 'main'), (FIRST_LOOK,))
        return repository

    def test_stage_links_the_declared_investigations(self, repository: TicketRepository) -> None:
        record = repository.stage(
            FIRST, create_section(FIRST, 'main'), (SECOND_LOOK, FIRST_LOOK, SECOND_LOOK)
        )

        assert record.investigations == (SECOND_LOOK, FIRST_LOOK)

    def test_restage_appends_only_new_investigations(self, linked: TicketRepository) -> None:
        record = linked.stage(FIRST, self.replacement, (SECOND_LOOK, FIRST_LOOK))

        assert record.investigations == (FIRST_LOOK, SECOND_LOOK)

    def test_restage_replaces_the_section(self, linked: TicketRepository) -> None:
        linked.stage(FIRST, self.replacement, ())

        assert linked.staged_ticket(FIRST).section == self.replacement

    def test_restage_keeps_the_status(
        self, linked: TicketRepository, open_of: Callable[[Slug], OpenTicket]
    ) -> None:
        linked.mark_in_progress(open_of(FIRST))

        record = linked.stage(FIRST, self.replacement, ())

        assert record.status == 'in-progress'

    def test_unknown_investigation_is_refused(self, repository: TicketRepository) -> None:
        with pytest.raises(UnknownInvestigationError):
            repository.stage(FIRST, create_section(FIRST, 'main'), (FIRST_LOOK, 'never-recorded'))

    def test_unknown_investigation_stages_nothing(self, repository: TicketRepository) -> None:
        with pytest.raises(UnknownInvestigationError):
            repository.stage(FIRST, create_section(FIRST, 'main'), ('never-recorded',))

        assert repository.ticket(FIRST) is None

    def test_staged_summary_secret_is_stored_redacted(self, repository: TicketRepository) -> None:
        section = create_section(FIRST, 'main')
        secret_section = replace(section, summary=redact(SECRET_SUMMARY))

        repository.stage(FIRST, secret_section, ())

        summary = repository.staged_ticket(FIRST).section.summary
        assert summary == 'rotate [REDACTED:api-key] soon'


class TestStatus:
    @pytest.fixture
    def staged(self, repository: TicketRepository) -> TicketRepository:
        repository.stage(FIRST, create_section(FIRST, 'main'), ())
        return repository

    def test_mark_in_progress_moves_a_staged_ticket(
        self, staged: TicketRepository, open_of: Callable[[Slug], OpenTicket]
    ) -> None:
        staged.mark_in_progress(open_of(FIRST))

        assert staged.staged_ticket(FIRST).status == 'in-progress'

    def test_mark_closed_closes_an_in_progress_ticket(
        self, staged: TicketRepository, open_of: Callable[[Slug], OpenTicket]
    ) -> None:
        staged.mark_in_progress(open_of(FIRST))

        staged.mark_closed(open_of(FIRST))

        assert staged.staged_ticket(FIRST).status == 'closed'


class TestTicketId:
    @pytest.fixture
    def staged(self, repository: TicketRepository) -> TicketRepository:
        repository.stage(FIRST, create_section(FIRST, 'main'), ())
        return repository

    def test_every_lookup_names_the_same_id(self, repository: TicketRepository) -> None:
        staged_id = repository.stage(FIRST, create_section(FIRST, 'main'), ()).id

        assert repository.staged_ticket(FIRST).id == staged_id

    def test_restage_keeps_the_id(self, staged: TicketRepository) -> None:
        before = staged.staged_ticket(FIRST).id

        restaged = staged.stage(FIRST, create_section(FIRST, 'feature'), ())

        assert restaged.id == before

    def test_status_change_keeps_the_id(
        self, staged: TicketRepository, open_of: Callable[[Slug], OpenTicket]
    ) -> None:
        before = staged.staged_ticket(FIRST).id

        staged.mark_in_progress(open_of(FIRST))

        assert staged.staged_ticket(FIRST).id == before

    def test_two_tickets_have_different_ids(self, staged: TicketRepository) -> None:
        second = staged.stage(SECOND, create_section(SECOND, 'main'), ())

        assert second.id != staged.staged_ticket(FIRST).id


class TestBranchQueries:
    @pytest.fixture
    def busy(self, repository: TicketRepository) -> TicketRepository:
        repository.stage(THIRD, create_section(THIRD, 'main'), ())
        repository.stage(FIRST, create_section(FIRST, 'main'), ())
        repository.stage(SECOND, create_section(SECOND, 'feature'), ())
        return repository

    @pytest.fixture
    def lone(
        self, busy: TicketRepository, open_of: Callable[[Slug], OpenTicket]
    ) -> TicketRepository:
        busy.mark_closed(open_of(THIRD))
        return busy

    def test_no_ticket_on_a_branch_names_none(self, busy: TicketRepository) -> None:
        assert busy.unclosed_on_branch('elsewhere') is None
        assert busy.all_unclosed_on_branch('elsewhere') == []

    def test_two_tickets_on_a_branch_name_none(self, busy: TicketRepository) -> None:
        assert busy.unclosed_on_branch('main') is None

    def test_all_unclosed_lists_in_slug_order(self, busy: TicketRepository) -> None:
        assert busy.all_unclosed_on_branch('main') == [FIRST, THIRD]

    def test_closed_tickets_are_left_out(self, lone: TicketRepository) -> None:
        assert lone.all_unclosed_on_branch('main') == [FIRST]

    def test_the_only_unclosed_ticket_is_named(self, lone: TicketRepository) -> None:
        assert lone.unclosed_on_branch('main') == FIRST
