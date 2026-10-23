"""Every review repository case runs against the sqlite store and the fake."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RunId, WriteLimitError
from mightymodels_core.reviews import (
    ReviewRepository,
    RunExistsError,
    RunNotFoundError,
)
from mightymodels_core.reviews.records import FINDINGS, RUNS_LISTED
from mightymodels_core.reviews.tests.fakes import FakeReviewRepository, ReviewLedger

from tests.core.reviews.conftest import (
    FIRST_RUN,
    OTHER_SLUG,
    SECOND_RUN,
    SLUG,
    UNSTARTED_RUN,
    create_finding,
    create_run,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.core.reviews.conftest import ReviewHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class KeyOrder:
    name: str
    keys: tuple[str, ...]
    expected: tuple[str, ...]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def finding_key_order_cases() -> pytest.MarkDecorator:
    cases = [
        KeyOrder(name='by-length', keys=('MV-10', 'MV-2'), expected=('MV-2', 'MV-10')),
        KeyOrder(
            name='same-length', keys=('UB-2', 'MV-3', 'MV-1'), expected=('MV-1', 'MV-3', 'UB-2')
        ),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestImplementations:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeReviewRepository(ledger=ReviewLedger()), ReviewRepository)

    def test_repository_satisfies_the_protocol(self, harness: ReviewHarness) -> None:
        assert isinstance(harness.reviews, ReviewRepository)


class TestRuns:
    @pytest.fixture
    def started(self, harness: ReviewHarness) -> ReviewHarness:
        harness.reviews.record_run(create_run())
        return harness

    def test_unstarted_run_reads_as_none(self, harness: ReviewHarness) -> None:
        assert harness.reviews.run(FIRST_RUN) is None

    def test_run_is_read_back_as_recorded(self, started: ReviewHarness) -> None:
        assert started.reviews.run(FIRST_RUN) == create_run()

    def test_started_run_is_read_back_as_recorded(self, started: ReviewHarness) -> None:
        assert started.reviews.started_run(FIRST_RUN) == create_run()

    def test_unstarted_run_is_refused_by_started_run(self, harness: ReviewHarness) -> None:
        with pytest.raises(RunNotFoundError):
            harness.reviews.started_run(UNSTARTED_RUN)

    def test_run_key_held_is_refused(self, started: ReviewHarness) -> None:
        with pytest.raises(RunExistsError):
            started.reviews.record_run(create_run())

    def test_run_without_a_ticket_is_read_back(self, harness: ReviewHarness) -> None:
        unticketed = create_run(slug=None)

        harness.reviews.record_run(unticketed)

        assert harness.reviews.run(FIRST_RUN) == unticketed

    def test_models_are_replaced(self, started: ReviewHarness) -> None:
        models = {'merge-vader': 'sonnet'}

        started.reviews.record_models(FIRST_RUN, models)

        assert started.reviews.started_run(FIRST_RUN) == replace(create_run(), models=models)

    def test_models_of_an_unstarted_run_are_refused(self, harness: ReviewHarness) -> None:
        with pytest.raises(RunNotFoundError):
            harness.reviews.record_models(UNSTARTED_RUN, {})


class TestLatestRuns:
    @pytest.fixture
    def two_runs(self, harness: ReviewHarness) -> ReviewHarness:
        harness.reviews.record_run(create_run(FIRST_RUN))
        harness.reviews.record_run(create_run(SECOND_RUN))
        return harness

    def test_no_runs_are_listed_before_one_starts(self, harness: ReviewHarness) -> None:
        latest = harness.reviews.latest_runs()

        assert (latest.rows, latest.older_left_out) == ((), False)

    def test_runs_are_listed_oldest_first(self, two_runs: ReviewHarness) -> None:
        latest = two_runs.reviews.latest_runs()

        assert [run.run_id for run in latest.rows] == [FIRST_RUN, SECOND_RUN]

    def test_newest_run_of_a_ticket_is_read(self, two_runs: ReviewHarness) -> None:
        latest = two_runs.reviews.latest_run(SLUG)

        assert latest is not None
        assert latest.run_id == SECOND_RUN

    def test_ticket_without_runs_reads_as_none(self, two_runs: ReviewHarness) -> None:
        assert two_runs.reviews.latest_run(OTHER_SLUG) is None


class TestRunsListed:
    @pytest.fixture
    def crowded(self, harness: ReviewHarness) -> ReviewHarness:
        for number in range(RUNS_LISTED.rows + 1):
            harness.reviews.record_run(create_run(RunId(f'20260101-{number:06d}')))
        return harness

    def test_listing_keeps_the_newest_runs(self, crowded: ReviewHarness) -> None:
        latest = crowded.reviews.latest_runs()

        assert len(latest.rows) == RUNS_LISTED.rows
        assert latest.older_left_out
        assert latest.rows[0].run_id == RunId('20260101-000001')


class TestFindings:
    @pytest.fixture
    def started(self, harness: ReviewHarness) -> ReviewHarness:
        harness.reviews.record_run(create_run())
        return harness

    def test_unstarted_run_holds_no_findings(self, harness: ReviewHarness) -> None:
        assert harness.reviews.findings(UNSTARTED_RUN) == []

    def test_findings_are_read_back_as_recorded(self, started: ReviewHarness) -> None:
        findings = [create_finding('MV-1'), create_finding('MV-2', with_evidence=False)]

        started.reviews.record_findings(FIRST_RUN, findings)

        assert started.reviews.findings(FIRST_RUN) == findings

    @finding_key_order_cases()
    def test_findings_are_ordered_by_key_length_then_key(
        self, started: ReviewHarness, case: KeyOrder
    ) -> None:
        started.reviews.record_findings(FIRST_RUN, [create_finding(key) for key in case.keys])

        keys = tuple(finding.key for finding in started.reviews.findings(FIRST_RUN))
        assert keys == case.expected

    def test_recorded_key_is_replaced(self, started: ReviewHarness) -> None:
        started.reviews.record_findings(FIRST_RUN, [create_finding('MV-1')])
        revised = create_finding('MV-1', title='a revised defect')

        started.reviews.record_findings(FIRST_RUN, [revised])

        assert started.reviews.findings(FIRST_RUN) == [revised]

    def test_findings_of_another_run_are_not_read(self, started: ReviewHarness) -> None:
        started.reviews.record_run(create_run(SECOND_RUN))
        started.reviews.record_findings(SECOND_RUN, [create_finding('MV-1')])

        assert started.reviews.findings(FIRST_RUN) == []

    def test_findings_of_an_unstarted_run_are_refused(self, harness: ReviewHarness) -> None:
        with pytest.raises(RunNotFoundError):
            harness.reviews.record_findings(UNSTARTED_RUN, [create_finding('MV-1')])


class TestFindingCap:
    held_findings = FINDINGS.rows

    @pytest.fixture
    def full_harness(self, harness: ReviewHarness) -> ReviewHarness:
        harness.reviews.record_run(create_run())
        findings = [create_finding(f'MV-{number}') for number in range(self.held_findings)]
        harness.reviews.record_findings(FIRST_RUN, findings)
        return harness

    def test_findings_at_the_cap_are_read_back(self, full_harness: ReviewHarness) -> None:
        assert len(full_harness.reviews.findings(FIRST_RUN)) == self.held_findings

    def test_finding_past_the_cap_is_refused(self, full_harness: ReviewHarness) -> None:
        with pytest.raises(WriteLimitError):
            full_harness.reviews.record_findings(FIRST_RUN, [create_finding('MV-over')])

    def test_held_key_at_the_cap_is_replaced(self, full_harness: ReviewHarness) -> None:
        revised = create_finding('MV-1', title='a revised defect')

        full_harness.reviews.record_findings(FIRST_RUN, [revised])

        assert revised in full_harness.reviews.findings(FIRST_RUN)

    def test_refused_batch_stores_none_of_it(self, full_harness: ReviewHarness) -> None:
        batch = [create_finding('MV-1', title='a revised defect'), create_finding('MV-over')]

        with pytest.raises(WriteLimitError):
            full_harness.reviews.record_findings(FIRST_RUN, batch)

        assert create_finding('MV-1') in full_harness.reviews.findings(FIRST_RUN)
