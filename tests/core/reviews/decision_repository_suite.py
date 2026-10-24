"""The review decision repository contract, written once for every tier to subclass."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.reviews import (
    ReviewDecisionRepository,
    RunNotFoundError,
    UndecidedFindingError,
    UnknownFindingError,
)

from tests.core.reviews.review_builders import (
    FIRST_RUN,
    SECOND_RUN,
    UNSTARTED_RUN,
    create_decided,
    create_finding,
    create_resolved,
    create_run,
)

if TYPE_CHECKING:
    from tests.core.reviews.review_builders import ReviewHarness


class DecisionRepositoryContract:
    class TestImplementations:
        def test_repository_satisfies_the_protocol(self, harness: ReviewHarness) -> None:
            assert isinstance(harness.decisions, ReviewDecisionRepository)

    class TestDispositions:
        @pytest.fixture
        def found(self, harness: ReviewHarness) -> ReviewHarness:
            harness.reviews.record_run(create_run())
            harness.reviews.record_findings(
                FIRST_RUN, [create_finding('MV-1'), create_finding('MV-2'), create_finding('MV-10')]
            )
            return harness

        def test_unstarted_run_holds_no_dispositions(self, harness: ReviewHarness) -> None:
            assert harness.decisions.dispositions(UNSTARTED_RUN) == []

        def test_dispositions_are_read_back_ordered_by_key(self, found: ReviewHarness) -> None:
            decided = [create_decided('MV-10'), create_decided('MV-2')]

            found.decisions.record_dispositions(FIRST_RUN, decided)

            assert found.decisions.dispositions(FIRST_RUN) == [decided[1], decided[0]]

        def test_recorded_disposition_is_replaced(self, found: ReviewHarness) -> None:
            found.decisions.record_dispositions(FIRST_RUN, [create_decided('MV-1')])
            revised = create_decided('MV-1', decision='defer')

            found.decisions.record_dispositions(FIRST_RUN, [revised])

            assert found.decisions.dispositions(FIRST_RUN) == [revised]

        def test_dispositions_of_another_run_are_not_read(self, found: ReviewHarness) -> None:
            found.reviews.record_run(create_run(SECOND_RUN))
            found.decisions.record_dispositions(FIRST_RUN, [create_decided('MV-1')])

            assert found.decisions.dispositions(SECOND_RUN) == []

        def test_unknown_finding_is_refused(self, found: ReviewHarness) -> None:
            with pytest.raises(UnknownFindingError):
                found.decisions.record_dispositions(FIRST_RUN, [create_decided('MV-9')])

        def test_refused_batch_stores_none_of_it(self, found: ReviewHarness) -> None:
            batch = [create_decided('MV-1'), create_decided('MV-9')]

            with pytest.raises(UnknownFindingError):
                found.decisions.record_dispositions(FIRST_RUN, batch)

            assert found.decisions.dispositions(FIRST_RUN) == []

        def test_unstarted_run_is_refused(self, harness: ReviewHarness) -> None:
            with pytest.raises(RunNotFoundError):
                harness.decisions.record_dispositions(UNSTARTED_RUN, [create_decided('MV-1')])

    class TestOutcomes:
        @pytest.fixture
        def decided(self, harness: ReviewHarness) -> ReviewHarness:
            harness.reviews.record_run(create_run())
            harness.reviews.record_findings(
                FIRST_RUN, [create_finding('MV-1'), create_finding('MV-2')]
            )
            harness.decisions.record_dispositions(FIRST_RUN, [create_decided('MV-1')])
            return harness

        def test_unstarted_run_holds_no_outcomes(self, harness: ReviewHarness) -> None:
            assert harness.decisions.outcomes(UNSTARTED_RUN) == []

        def test_outcome_is_read_back_as_recorded(self, decided: ReviewHarness) -> None:
            resolved = create_resolved('MV-1')

            decided.decisions.record_outcome(FIRST_RUN, resolved)

            assert decided.decisions.outcomes(FIRST_RUN) == [resolved]

        def test_recorded_outcome_is_replaced(self, decided: ReviewHarness) -> None:
            decided.decisions.record_outcome(FIRST_RUN, create_resolved('MV-1'))
            revised = create_resolved('MV-1', result='failed')

            decided.decisions.record_outcome(FIRST_RUN, revised)

            assert decided.decisions.outcomes(FIRST_RUN) == [revised]

        def test_finding_without_a_disposition_is_refused(self, decided: ReviewHarness) -> None:
            with pytest.raises(UndecidedFindingError):
                decided.decisions.record_outcome(FIRST_RUN, create_resolved('MV-2'))

        def test_unknown_finding_is_refused(self, decided: ReviewHarness) -> None:
            with pytest.raises(UndecidedFindingError):
                decided.decisions.record_outcome(FIRST_RUN, create_resolved('MV-9'))

        def test_unstarted_run_is_refused(self, harness: ReviewHarness) -> None:
            with pytest.raises(RunNotFoundError):
                harness.decisions.record_outcome(UNSTARTED_RUN, create_resolved('MV-1'))

    class TestReopen:
        @pytest.fixture
        def resolved(self, harness: ReviewHarness) -> ReviewHarness:
            harness.reviews.record_run(create_run())
            harness.reviews.record_findings(
                FIRST_RUN, [create_finding('MV-1'), create_finding('MV-2')]
            )
            harness.decisions.record_dispositions(
                FIRST_RUN, [create_decided('MV-1'), create_decided('MV-2')]
            )
            harness.decisions.record_outcome(FIRST_RUN, create_resolved('MV-1'))
            harness.decisions.record_outcome(FIRST_RUN, create_resolved('MV-2'))
            return harness

        def test_reopened_finding_loses_its_disposition_and_outcome(
            self, resolved: ReviewHarness
        ) -> None:
            resolved.decisions.reopen(FIRST_RUN, ['MV-1'])

            assert resolved.decisions.dispositions(FIRST_RUN) == [create_decided('MV-2')]
            assert resolved.decisions.outcomes(FIRST_RUN) == [create_resolved('MV-2')]

        def test_reopened_finding_may_be_decided_again(self, resolved: ReviewHarness) -> None:
            resolved.decisions.reopen(FIRST_RUN, ['MV-1'])
            revised = create_decided('MV-1', decision='defer')

            resolved.decisions.record_dispositions(FIRST_RUN, [revised])

            assert revised in resolved.decisions.dispositions(FIRST_RUN)

        def test_finding_never_decided_is_reopened_quietly(self, resolved: ReviewHarness) -> None:
            resolved.decisions.reopen(FIRST_RUN, ['MV-9'])

            assert len(resolved.decisions.dispositions(FIRST_RUN)) == 2

        def test_unstarted_run_is_reopened_quietly(self, harness: ReviewHarness) -> None:
            harness.decisions.reopen(UNSTARTED_RUN, ['MV-1'])

            assert harness.decisions.dispositions(UNSTARTED_RUN) == []
