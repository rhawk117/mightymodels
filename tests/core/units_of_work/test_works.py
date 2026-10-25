from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import SqliteContractRepository
from mightymodels_core.crashouts import SqliteCrashoutRepository
from mightymodels_core.investigations import SqliteInvestigationRepository
from mightymodels_core.reviews import SqliteReviewDecisionRepository, SqliteReviewRepository
from mightymodels_core.similarity import SqliteScoutReportRepository, SqliteSimilarityRepository
from mightymodels_core.tasks import SqliteAttemptRepository, SqliteTaskRepository
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import UnknownRepositoryError

if TYPE_CHECKING:
    from mightymodels_core.database import Unit
    from mightymodels_core.units_of_work import (
        InvestigationWork,
        JournalWork,
        ReviewWork,
        TaskWork,
    )


pytestmark = [pytest.mark.integration]

SQLITE_STORES = (
    SqliteAttemptRepository,
    SqliteContractRepository,
    SqliteCrashoutRepository,
    SqliteInvestigationRepository,
    SqliteReviewDecisionRepository,
    SqliteReviewRepository,
    SqliteScoutReportRepository,
    SqliteSimilarityRepository,
    SqliteTaskRepository,
    SqliteTicketRepository,
)


def unit_of(store: object) -> Unit:
    assert isinstance(store, SQLITE_STORES)
    return store.unit


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
    def test_read_unit_refuses_a_repository_the_database_lacks(self, task_work: TaskWork) -> None:
        with pytest.raises(UnknownRepositoryError), task_work.read():
            pass
