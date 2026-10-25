"""The unit-of-work tests, written once for every tier to subclass."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import UnitExitedError
from mightymodels_core.primitives import Slug
from mightymodels_core.schemas.repositories import REPOSITORY_BY_KEY, RepositoryKeyParams
from mightymodels_core.snapshot import RepositoryFacts, SnapshotRequest
from mightymodels_core.tickets import NotStagedError, TicketExistsError
from mightymodels_core.units_of_work import (
    MissingTicketError,
    UnknownRepositoryError,
    read_entry,
    write_entry,
)

from tests.core.units_of_work.units_of_work_builders import (
    REVIEW_RUN,
    TASK,
    count_repositories,
    unit_of,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database
    from mightymodels_core.primitives import RepositoryKey, RunId
    from mightymodels_core.tickets import TicketAnswers
    from mightymodels_core.units_of_work import (
        InvestigationWork,
        JournalWork,
        ReviewWork,
        SnapshotRead,
        TaskWork,
        TicketWork,
    )
    from mightymodels_core.workspace import Workspace


class UnitsOfWorkFastPaths:
    class TestTicketWorkRepository:
        def test_other_repository_does_not_see_the_staged_ticket(
            self, other_ticket_work: TicketWork, staged_ticket: Slug
        ) -> None:
            with other_ticket_work.read() as unit:
                assert unit.tickets.tickets.ticket(staged_ticket) is None

    class TestInvestigationWorkRepository:
        def test_other_repository_does_not_see_the_investigation(
            self,
            other_investigation_work: InvestigationWork,
            started_investigation: Slug,
        ) -> None:
            with other_investigation_work.read() as unit:
                assert (
                    unit.investigations.investigations.investigation(started_investigation) is None
                )

    class TestTaskWorkRepository:
        def test_other_repository_does_not_see_the_staged_ticket(
            self, other_task_work: TaskWork, staged_slug: Slug
        ) -> None:
            with other_task_work.read() as unit:
                assert unit.tasks.tickets.ticket(staged_slug) is None

    class TestReviewWorkRepository:
        def test_other_repository_does_not_see_the_review_run(
            self, other_review_work: ReviewWork, started_review: RunId
        ) -> None:
            with other_review_work.read() as unit:
                assert unit.reviews.reviews.run(started_review) is None

    @pytest.mark.usefixtures('journaled')
    class TestJournalWorkRepository:
        def test_other_repository_does_not_see_the_crashout(
            self, other_journal_work: JournalWork
        ) -> None:
            with other_journal_work.read() as unit:
                assert unit.crashouts.last() is None

    class TestSnapshotReadRepository:
        facts = RepositoryFacts(branch='feat/widget', head='a' * 40, dirty=(), refusal=None)

        @pytest.fixture
        def request_for_staged_ticket(self, staged_slug: Slug) -> SnapshotRequest:
            return SnapshotRequest(slug=staged_slug, repository=self.facts)

        def test_other_repository_cannot_snapshot_the_staged_ticket(
            self, other_snapshot_read: SnapshotRead, request_for_staged_ticket: SnapshotRequest
        ) -> None:
            with pytest.raises(NotStagedError), other_snapshot_read.read() as unit:
                unit.snapshots.take(request_for_staged_ticket)


class UnitsOfWorkContract(UnitsOfWorkFastPaths):
    class TestReadEntry:
        def test_unknown_repository_key_is_refused_naming_the_key(
            self, database: Database, repository_key: RepositoryKey
        ) -> None:
            with (
                pytest.raises(UnknownRepositoryError) as refusal,
                read_entry(database, repository_key),
            ):
                pytest.fail('the read entry handed out a unit for an unknown key')

            assert refusal.value.repository_key == repository_key
            assert repository_key in str(refusal.value)

        def test_unknown_repository_key_is_not_recorded(
            self, database: Database, repository_key: RepositoryKey
        ) -> None:
            with pytest.raises(UnknownRepositoryError), read_entry(database, repository_key):
                pytest.fail('the read entry handed out a unit for an unknown key')

            assert count_repositories(database, repository_key) == 0

        def test_known_repository_key_yields_the_recorded_id(
            self, database: Database, repository_key: RepositoryKey
        ) -> None:
            with write_entry(database, repository_key) as written:
                pass

            with read_entry(database, repository_key) as read:
                assert read.repository_id == written.repository_id

    class TestWriteEntry:
        def test_ensures_the_repository_row(
            self, database: Database, repository_key: RepositoryKey
        ) -> None:
            with pytest.raises(UnknownRepositoryError), read_entry(database, repository_key):
                pytest.fail('the repository existed before the write entry')

            with write_entry(database, repository_key) as entry:
                assert entry.repository_id > 0

            assert count_repositories(database, repository_key) == 1

        def test_second_entry_resolves_the_same_id(
            self, database: Database, repository_key: RepositoryKey
        ) -> None:
            with write_entry(database, repository_key) as first:
                pass

            with write_entry(database, repository_key) as second:
                assert second.repository_id == first.repository_id

        def test_failure_in_the_scope_rolls_the_row_back(
            self, database: Database, repository_key: RepositoryKey
        ) -> None:
            with pytest.raises(ZeroDivisionError), write_entry(database, repository_key):
                raise ZeroDivisionError

            assert count_repositories(database, repository_key) == 0

        def test_unit_is_unusable_after_the_scope(
            self, database: Database, repository_key: RepositoryKey
        ) -> None:
            with write_entry(database, repository_key) as entry:
                pass

            with pytest.raises(UnitExitedError):
                entry.unit.one(
                    REPOSITORY_BY_KEY, RepositoryKeyParams(repository_key=repository_key)
                )

    class TestWriteUnitRollback:
        def test_error_in_a_write_unit_rolls_back_every_repositorys_writes(
            self, ticket_work: TicketWork, slug: Slug, failed_ticket_id: int
        ) -> None:
            with ticket_work.write() as unit:
                assert unit.tickets.tickets.ticket(slug) is None
                assert unit.tickets.investigations.investigation(Slug('first-look')) is None
                assert unit.closing.tasks.task(failed_ticket_id, TASK) is None
                assert unit.closing.attempts.failed_fixes(failed_ticket_id, TASK) == []
                assert unit.closing.contracts.commands(failed_ticket_id) == []
                assert unit.closing.review_decisions.reviews.run(REVIEW_RUN) is None
                assert unit.closing.review_decisions.decisions.dispositions(REVIEW_RUN) == []
                assert unit.closing.closings.closing(failed_ticket_id) is None

        @pytest.mark.usefixtures('failed_ticket_id')
        def test_error_in_a_write_unit_leaves_the_stored_file_in_place(
            self, ticket_work: TicketWork, slug: Slug, written_text: str
        ) -> None:
            with ticket_work.read() as unit:
                assert unit.files.source(slug).text == written_text

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

    class TestInvestigationWork:
        def test_write_unit_holds_the_service_with_the_injected_clock(
            self, investigation_work: InvestigationWork
        ) -> None:
            with investigation_work.write() as unit:
                assert unit.investigations.clock is investigation_work.clock

        def test_service_stores_share_one_unit(self, investigation_work: InvestigationWork) -> None:
            with investigation_work.write() as unit:
                service = unit.investigations

                assert unit_of(service.investigations) is unit_of(service.similarity)

    class TestTaskWork:
        def test_write_unit_holds_both_services_with_the_injected_clock(
            self, task_work: TaskWork
        ) -> None:
            with task_work.write() as unit:
                assert unit.tasks.clock is task_work.clock
                assert unit.contracts.clock is task_work.clock

        def test_task_and_contract_services_share_one_unit(self, task_work: TaskWork) -> None:
            with task_work.write() as unit:
                tasks = unit.tasks

                assert unit_of(tasks.tasks) is unit_of(tasks.attempts)
                assert tasks.contracts is unit.contracts.contracts
                assert unit_of(tasks.contracts) is unit_of(tasks.tasks)
                assert tasks.tickets is unit.contracts.tickets
                assert unit_of(tasks.tickets) is unit_of(tasks.tasks)

    class TestReviewWork:
        def test_write_unit_holds_both_services_with_the_injected_clock(
            self, review_work: ReviewWork
        ) -> None:
            with review_work.write() as unit:
                assert unit.reviews.clock is review_work.clock
                assert unit.decisions.clock is review_work.clock

        def test_review_and_decision_services_share_one_unit(self, review_work: ReviewWork) -> None:
            with review_work.write() as unit:
                reviews = unit.reviews

                assert reviews.reviews is unit.decisions.reviews
                assert reviews.decisions is unit.decisions.decisions
                assert unit_of(reviews.reviews) is unit_of(reviews.decisions)
                assert unit_of(reviews.reviews) is unit_of(reviews.similarity)

    class TestJournalWork:
        def test_write_unit_holds_the_crashout_service_with_the_injected_clock(
            self, journal_work: JournalWork
        ) -> None:
            with journal_work.write() as unit:
                assert unit.crashouts.clock is journal_work.clock

        def test_crashout_and_similarity_services_share_one_unit(
            self, journal_work: JournalWork
        ) -> None:
            with journal_work.write() as unit:
                crashouts = unit.crashouts

                assert crashouts.similarity is unit.similarity.similarity
                assert unit_of(crashouts.crashouts) is unit_of(crashouts.similarity)
                assert unit_of(unit.similarity.scouts) is unit_of(crashouts.similarity)

    class TestUnknownRepository:
        def test_read_unit_refuses_a_repository_the_database_lacks(
            self, task_work: TaskWork
        ) -> None:
            with pytest.raises(UnknownRepositoryError), task_work.read():
                pass
