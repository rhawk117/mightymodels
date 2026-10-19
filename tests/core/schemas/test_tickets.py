from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.schemas.investigations import ADD_INVESTIGATION, AddInvestigationParams
from mightymodels_core.schemas.repositories import (
    ENSURE_REPOSITORY,
    REPOSITORY_BY_KEY,
    RepositoryKeyParams,
)
from mightymodels_core.schemas.tickets import (
    CLOSING_OF_TICKET,
    LINK_TICKET_INVESTIGATION,
    SET_TICKET_STATUS,
    STAGE_TICKET,
    TICKET_BY_ID,
    TICKET_BY_SLUG,
    UNCLOSED_SLUG_PAIR_ON_BRANCH,
    UNCLOSED_SLUGS_ON_BRANCH,
    UPSERT_CLOSING,
    BranchParams,
    ClosingParams,
    LinkTicketInvestigationParams,
    SetTicketStatusParams,
    StageTicketParams,
    TicketIdParams,
    TicketSlugParams,
    UpsertClosingParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database

pytestmark = pytest.mark.integration

VALIDATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def stage_params(repository_id: int, slug: str, branch: str = 'main') -> StageTicketParams:
    return StageTicketParams(
        repository_id=repository_id,
        slug=slug,
        ticket=f'ticket {slug}',
        summary='summary',
        branch=branch,
        scope='med',
        plan_first=True,
        auto_escalate=False,
        issue=7,
        jira=None,
        models={'engineer': 'sonnet', 'intern': None},
        context=['first', 'second'],
        validated_at=VALIDATED_AT,
    )


def stage(database: Database, params: StageTicketParams) -> int:
    with database.write() as unit:
        staged = unit.one(STAGE_TICKET, params)
    assert staged is not None
    return staged.id


class TestRepositories:
    def test_ensuring_a_repository_twice_returns_the_same_row(self, database: Database) -> None:
        key = RepositoryKeyParams(repository_key='owner/repo')
        with database.write() as unit:
            first = unit.one(ENSURE_REPOSITORY, key)
            second = unit.one(ENSURE_REPOSITORY, key)

        assert first is not None
        assert first == second
        assert first.repository_key == 'owner/repo'

    def test_a_repository_is_found_by_its_key(self, database: Database, repository_id: int) -> None:
        with database.read() as unit:
            found = unit.one(REPOSITORY_BY_KEY, RepositoryKeyParams(repository_key='owner/repo'))
            missing = unit.one(REPOSITORY_BY_KEY, RepositoryKeyParams(repository_key='other'))

        assert found is not None
        assert found.id == repository_id
        assert missing is None


class TestTickets:
    def test_a_staged_ticket_reads_back_by_slug_and_by_id(
        self, database: Database, repository_id: int
    ) -> None:
        ticket_id = stage(database, stage_params(repository_id, 'first'))

        with database.read() as unit:
            by_slug = unit.one(
                TICKET_BY_SLUG, TicketSlugParams(repository_id=repository_id, slug='first')
            )
            by_id = unit.one(TICKET_BY_ID, TicketIdParams(id=ticket_id))

        assert by_slug is not None
        assert by_slug == by_id
        assert by_slug.status == 'staged'
        assert by_slug.scope == 'med'
        assert by_slug.plan_first is True
        assert by_slug.models == {'engineer': 'sonnet', 'intern': None}
        assert by_slug.context == ['first', 'second']
        assert by_slug.validated_at == VALIDATED_AT
        assert by_slug.investigations == []

    def test_restaging_updates_the_ticket_and_keeps_its_status(
        self, database: Database, repository_id: int
    ) -> None:
        first = stage(database, stage_params(repository_id, 'first'))
        slug = TicketSlugParams(repository_id=repository_id, slug='first')
        with database.write() as unit:
            unit.run(
                SET_TICKET_STATUS,
                SetTicketStatusParams(
                    repository_id=repository_id, slug='first', status='in-progress'
                ),
            )
        again = stage(database, stage_params(repository_id, 'first', branch='next'))

        with database.read() as unit:
            ticket = unit.one(TICKET_BY_SLUG, slug)

        assert again == first
        assert ticket is not None
        assert ticket.branch == 'next'
        assert ticket.status == 'in-progress'

    def test_a_status_update_reports_whether_a_ticket_matched(
        self, database: Database, repository_id: int
    ) -> None:
        stage(database, stage_params(repository_id, 'first'))

        def update(slug: str) -> int:
            params = SetTicketStatusParams(repository_id=repository_id, slug=slug, status='closed')
            with database.write() as unit:
                return unit.run(SET_TICKET_STATUS, params)

        assert update('first') == 1
        assert update('absent') == 0

    def test_unclosed_slugs_on_a_branch_exclude_closed_tickets(
        self, database: Database, repository_id: int
    ) -> None:
        for slug in ('beta', 'alpha', 'done'):
            stage(database, stage_params(repository_id, slug))
        stage(database, stage_params(repository_id, 'elsewhere', branch='other'))
        with database.write() as unit:
            unit.run(
                SET_TICKET_STATUS,
                SetTicketStatusParams(repository_id=repository_id, slug='done', status='closed'),
            )

        branch = BranchParams(repository_id=repository_id, branch='main')
        with database.read() as unit:
            ordered = unit.all(UNCLOSED_SLUGS_ON_BRANCH, branch)
            pair = unit.all(UNCLOSED_SLUG_PAIR_ON_BRANCH, branch)

        assert [row.slug for row in ordered] == ['alpha', 'beta']
        assert {row.slug for row in pair} == {'alpha', 'beta'}


class TestTicketInvestigations:
    @pytest.fixture
    def linked(self, database: Database, repository_id: int) -> int:
        ticket_id = stage(database, stage_params(repository_id, 'first'))
        link_params = []
        with database.write() as unit:
            for key in ('probe', 'survey'):
                investigation = unit.one(
                    ADD_INVESTIGATION,
                    AddInvestigationParams(
                        repository_id=repository_id,
                        investigation_key=key,
                        target='target',
                        kind='known',
                    ),
                )
                assert investigation is not None
                link_params.append(
                    LinkTicketInvestigationParams(
                        ticket_id=ticket_id, investigation_id=investigation.id
                    )
                )
            unit.run_many(LINK_TICKET_INVESTIGATION, link_params)
            unit.run_many(LINK_TICKET_INVESTIGATION, link_params)
        return ticket_id

    def test_links_read_back_in_link_order_and_repeat_links_are_ignored(
        self, database: Database, linked: int
    ) -> None:
        with database.read() as unit:
            ticket = unit.one(TICKET_BY_ID, TicketIdParams(id=linked))

        assert ticket is not None
        assert ticket.investigations == ['probe', 'survey']


class TestClosings:
    @pytest.fixture
    def ticket_id(self, database: Database, repository_id: int) -> int:
        return stage(database, stage_params(repository_id, 'first'))

    def closing(self, ticket_id: int, shipped: str) -> UpsertClosingParams:
        return UpsertClosingParams(
            ticket_id=ticket_id,
            closed_at=VALIDATED_AT,
            head='abc123',
            shipped=shipped,
            pr=None,
            gotchas=['one'],
            archive='archive.md',
        )

    def test_a_second_closing_replaces_the_first(self, database: Database, ticket_id: int) -> None:
        with database.write() as unit:
            unit.run(UPSERT_CLOSING, self.closing(ticket_id, 'first'))
            unit.run(UPSERT_CLOSING, self.closing(ticket_id, 'second'))

        with database.read() as unit:
            closing = unit.one(CLOSING_OF_TICKET, ClosingParams(ticket_id=ticket_id))

        assert closing is not None
        assert closing.shipped == 'second'
        assert closing.closed_at == VALIDATED_AT
        assert closing.gotchas == ['one']
        assert closing.pr is None
