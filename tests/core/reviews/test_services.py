"""The review service over the fake repositories: start, override, add, gate, report and list."""

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RunId
from mightymodels_core.reviews import (
    BaseRequiredError,
    OverrideSpentError,
    RunExistsError,
    RunNotFoundError,
    SourcesRequiredError,
)
from mightymodels_core.reviews.records import RUNS_LISTED

from .conftest import (
    HEAD,
    OTHER_SLUG,
    SERVICE_MOMENT,
    SERVICE_RUN,
    UNSTARTED_RUN,
    Case,
    create_decided,
    create_gate_finding,
    create_incoming,
    create_request,
    create_resolved,
    create_run,
)

if TYPE_CHECKING:
    from mightymodels_core.reviews import FindingRecord, Verdict
    from mightymodels_core.schemas.reviews import Decision, FindingSeverity, Result

    from .conftest import ServiceHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class GateState:
    findings: list[FindingRecord]
    decisions: dict[str, Decision] = field(default_factory=dict)
    results: dict[str, Result] = field(default_factory=dict)


def arrange_state(harness: ServiceHarness, state: GateState) -> None:
    decided = [create_decided(key, decision=choice) for key, choice in state.decisions.items()]
    resolved = [create_resolved(key, result=result) for key, result in state.results.items()]
    harness.reviews.record_findings(SERVICE_RUN, state.findings)
    harness.decisions.record_dispositions(SERVICE_RUN, decided)
    for outcome in resolved:
        harness.decisions.record_outcome(SERVICE_RUN, outcome)


def one(severity: FindingSeverity) -> list[FindingRecord]:
    return [create_gate_finding('F1', 'MV-1', severity)]


def gate_order_cases() -> pytest.MarkDecorator:
    def finding(key: str, source: str, **changes: object) -> FindingRecord:
        return replace(create_gate_finding(key, source), **changes)

    mixed = [
        finding('F1', 'MV-1', severity='Low'),
        finding('F2', 'UB-2'),
        finding('F3', 'MV-3'),
        finding('F4', 'UB-4', severity='Critical'),
        finding('F5', 'UB-5', security=True),
    ]
    numbered = [finding('F10', 'MV-1'), finding('F9', 'MV-2')]
    merged = [finding('F1', 'UB-1'), finding('F2', 'UB-2', sources=('UB-2', 'MV-2'))]
    cases = [
        Case(name='severity-security-weight', given=mixed, expected=['F4', 'F5', 'F3', 'F2', 'F1']),
        Case(name='key-number-not-text', given=numbered, expected=['F9', 'F10']),
        Case(name='merged-source-heaviest', given=merged, expected=['F2', 'F1']),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


def verdict_cases() -> pytest.MarkDecorator:
    def state(
        severity: FindingSeverity,
        decisions: dict[str, Decision] | None = None,
        results: dict[str, Result] | None = None,
    ) -> GateState:
        return GateState(findings=one(severity), decisions=decisions or {}, results=results or {})

    cases = [
        Case(name='no-findings', given=GateState(findings=[]), expected='CLEAR'),
        Case(name='open-high', given=state('High'), expected='BLOCK'),
        Case(
            name='high-accepted',
            given=state('High', decisions={'F1': 'accept-risk'}),
            expected='MERGE WITH CONDITIONS',
        ),
        Case(
            name='critical-accepted',
            given=state('Critical', decisions={'F1': 'accept-risk'}),
            expected='BLOCK',
        ),
        Case(
            name='high-deferred', given=state('High', decisions={'F1': 'defer'}), expected='BLOCK'
        ),
        Case(
            name='high-dismissed',
            given=state('High', decisions={'F1': 'dismiss'}),
            expected='CLEAR',
        ),
        Case(
            name='high-fixed',
            given=state('High', decisions={'F1': 'fix'}, results={'F1': 'fixed'}),
            expected='CLEAR',
        ),
        Case(
            name='fix-failed-stays-open',
            given=state('High', decisions={'F1': 'fix'}, results={'F1': 'failed'}),
            expected='BLOCK',
        ),
        Case(name='open-medium', given=state('Medium'), expected='MERGE WITH CONDITIONS'),
        Case(name='open-low', given=state('Low'), expected='CLEAR'),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestStart:
    def test_run_records_head_and_the_clock_time(self, service_harness: ServiceHarness) -> None:
        run = service_harness.service.start(create_request(), HEAD)

        assert service_harness.reviews.run(SERVICE_RUN) == run
        assert (run.head, run.created_at) == (HEAD, SERVICE_MOMENT)

    def test_run_id_that_exists_is_refused(self, started_harness: ServiceHarness) -> None:
        with pytest.raises(RunExistsError):
            started_harness.service.start(create_request(), HEAD)

        assert len(started_harness.reviews.latest_runs().rows) == 1

    def test_refused_target_writes_no_run(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(BaseRequiredError):
            service_harness.service.start(create_request(scope='branch'), HEAD)

        assert service_harness.reviews.run(SERVICE_RUN) is None


class TestOverride:
    def test_override_moves_the_heavier_persona_and_stores_it(
        self, started_harness: ServiceHarness
    ) -> None:
        run = started_harness.service.override(SERVICE_RUN)

        assert run.models == {'merge-vader': 'fable', 'uncle-bob': 'opus'}
        assert started_harness.reviews.started_run(SERVICE_RUN).models == run.models

    def test_second_override_is_refused(self, started_harness: ServiceHarness) -> None:
        started_harness.service.override(SERVICE_RUN)

        with pytest.raises(OverrideSpentError):
            started_harness.service.override(SERVICE_RUN)

    def test_unknown_run_is_refused(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(RunNotFoundError):
            service_harness.service.override(UNSTARTED_RUN)


class TestAddFindings:
    first = create_incoming('MV-1', 'src/a.py:10', severity='Medium')
    second = create_incoming('MV-2', 'src/b.py:5')
    overlapping = create_incoming('UB-1', 'src/a.py:10')

    def test_unknown_run_is_refused(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(RunNotFoundError):
            service_harness.service.add_findings(UNSTARTED_RUN, [self.first])

    def test_findings_are_numbered_stored_and_recorded_for_similarity(
        self, started_harness: ServiceHarness
    ) -> None:
        added = started_harness.service.add_findings(SERVICE_RUN, [self.first, self.second])

        assert [finding.key for finding in added.changed] == ['F1', 'F2']
        assert added.received == 2
        assert started_harness.similarity.entry('review-finding', f'{SERVICE_RUN} F2') is not None

    def test_malformed_finding_writes_nothing(self, started_harness: ServiceHarness) -> None:
        unsourced = replace(self.second, sources=())

        with pytest.raises(SourcesRequiredError):
            started_harness.service.add_findings(SERVICE_RUN, [self.first, unsourced])

        assert started_harness.reviews.findings(SERVICE_RUN) == []

    def test_batch_reopens_only_the_decided_findings_it_changed(
        self, started_harness: ServiceHarness
    ) -> None:
        service = started_harness.service
        service.add_findings(SERVICE_RUN, [self.first, self.second])
        decided = [create_decided('F1'), create_decided('F2')]
        started_harness.decisions.record_dispositions(SERVICE_RUN, decided)

        added = service.add_findings(SERVICE_RUN, [self.overlapping])

        remaining = started_harness.decisions.dispositions(SERVICE_RUN)
        assert added.reopened == ('F1',)
        assert [item.finding_key for item in remaining] == ['F2']


class TestGateAndReport:
    @pytest.mark.parametrize('read', ['gate', 'report'])
    def test_unknown_run_is_refused(self, service_harness: ServiceHarness, read: str) -> None:
        with pytest.raises(RunNotFoundError):
            getattr(service_harness.service, read)(UNSTARTED_RUN)

    @gate_order_cases()
    def test_gate_order(
        self, started_harness: ServiceHarness, case: Case[list[FindingRecord], list[str]]
    ) -> None:
        arrange_state(started_harness, GateState(findings=case.given))

        report = started_harness.service.gate(SERVICE_RUN)

        assert [finding.key for finding in report.findings] == case.expected

    @verdict_cases()
    def test_verdict(self, started_harness: ServiceHarness, case: Case[GateState, Verdict]) -> None:
        arrange_state(started_harness, case.given)

        assert started_harness.service.report(SERVICE_RUN).verdict == case.expected

    def test_report_keeps_the_recorded_order(self, started_harness: ServiceHarness) -> None:
        low, critical = (
            create_gate_finding('F1', 'MV-1', 'Low'),
            create_gate_finding('F2', 'MV-2', 'Critical'),
        )
        arrange_state(started_harness, GateState(findings=[low, critical]))

        report = started_harness.service.report(SERVICE_RUN)

        assert [finding.key for finding in report.findings] == ['F1', 'F2']


class TestListing:
    def test_no_runs_lists_nothing(self, service_harness: ServiceHarness) -> None:
        listing = service_harness.service.listing()

        assert (listing.runs, listing.older_left_out) == ((), False)

    def test_run_is_listed_with_its_finding_count_and_verdict(
        self, started_harness: ServiceHarness
    ) -> None:
        arrange_state(started_harness, GateState(findings=one('High')))

        (summary,) = started_harness.service.listing().runs

        assert (summary.run.run_id, summary.finding_count, summary.verdict) == (
            SERVICE_RUN,
            1,
            'BLOCK',
        )

    @pytest.fixture
    def overfull_harness(self, service_harness: ServiceHarness) -> ServiceHarness:
        for number in range(1, RUNS_LISTED.rows + 2):
            service_harness.reviews.record_run(create_run(RunId(f'20260101-{number:06d}')))
        return service_harness

    @pytest.fixture
    def described_harness(self, service_harness: ServiceHarness) -> ServiceHarness:
        described = replace(create_run(), slug=OTHER_SLUG, depth='deep')
        service_harness.reviews.record_run(described)
        return service_harness

    def test_runs_past_the_limit_are_left_out_and_flagged(
        self, overfull_harness: ServiceHarness
    ) -> None:
        listing = overfull_harness.service.listing()

        listed = sorted(summary.run.run_id for summary in listing.runs)
        newest_first = sorted(overfull_harness.reviews.ledger.runs, reverse=True)
        assert (listed, listing.older_left_out) == (sorted(newest_first[: RUNS_LISTED.rows]), True)

    def test_runs_within_the_limit_are_not_flagged(self, described_harness: ServiceHarness) -> None:
        assert described_harness.service.listing().older_left_out is False

    def test_listed_run_carries_its_slug_and_depth(self, described_harness: ServiceHarness) -> None:
        (summary,) = described_harness.service.listing().runs

        assert (summary.run.slug, summary.run.depth) == (OTHER_SLUG, 'deep')
