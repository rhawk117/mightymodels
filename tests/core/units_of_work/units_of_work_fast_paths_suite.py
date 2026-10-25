"""The unit-of-work fast paths, written once for every tier to subclass."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.snapshot import RepositoryFacts, SnapshotRequest
from mightymodels_core.tickets import NotStagedError

if TYPE_CHECKING:
    from mightymodels_core.primitives import RunId, Slug
    from mightymodels_core.units_of_work import (
        InvestigationWork,
        JournalWork,
        ReviewWork,
        SnapshotRead,
        TaskWork,
        TicketWork,
    )


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
