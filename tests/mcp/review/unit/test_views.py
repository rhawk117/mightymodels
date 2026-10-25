from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.primitives import RunId, Slug, create_routing_table, redact
from mightymodels_core.reviews import (
    AddedFindings,
    Evidence,
    FindingRecord,
    ReviewReport,
    ReviewRunRecord,
    RunListing,
    create_gate_policy,
)
from mightymodels_core.reviews.records import DecidedFinding, ResolvedFinding
from mightymodels_core.reviews.services import RunSummary
from mightymodels_core.similarity.records import Duplicate, Match
from mightymodels_mcp.review.views import (
    COMMENT_LIMIT,
    NO_RUNS,
    render_added,
    render_gate,
    render_listing,
    render_overridden,
    render_report,
    render_started,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.reviews import Verdict
    from mightymodels_core.vocabulary.reviews import Decision, Result, StoredSeverity

RUN = RunId('20260101-000001')
HEAD = 'a' * 40
MOMENT = datetime(2026, 1, 1, 3, 4, 5, tzinfo=UTC)


def create_run(*, base: str | None = 'main', slug: Slug | None = None) -> ReviewRunRecord:
    return ReviewRunRecord(
        run_id=RUN,
        slug=slug,
        scope='branch',
        base=base,
        head=HEAD,
        depth='standard',
        emphasis='release-readiness',
        weights={'merge-vader': 0.7, 'uncle-bob': 0.3},
        personas=('merge-vader', 'uncle-bob'),
        models={'merge-vader': 'opus', 'uncle-bob': 'opus'},
        created_at=MOMENT,
    )


def create_finding(
    number: int,
    *,
    severity: StoredSeverity = 'High',
    source: str = 'MV',
    security: bool = False,
    kind: str = 'defect',
    conflict: str | None = None,
    with_evidence: bool = False,
) -> FindingRecord:
    return FindingRecord(
        key=f'F{number}',
        sources=(f'{source}-{number}',),
        severity=severity,
        kind='quality' if kind == 'quality' else 'defect',
        security=security,
        title=redact(f'title {number}'),
        location=redact(f'src/a.py:{number}'),
        fix=redact(f'fix {number}'),
        verify=redact('pytest -q'),
        evidence=Evidence(kind='metric', cite=redact('churn 9')) if with_evidence else None,
        conflict=None if conflict is None else redact(conflict),
    )


def create_report(
    findings: Sequence[FindingRecord],
    *,
    decisions: dict[str, Decision] | None = None,
    results: dict[str, Result] | None = None,
) -> ReviewReport:
    run = create_run()
    decided = [
        DecidedFinding(
            finding_key=key, decision=decision, reason=redact('r'), by=redact('owner'), at=MOMENT
        )
        for key, decision in (decisions or {}).items()
    ]
    resolved = [
        ResolvedFinding(
            finding_key=key, result=result, commit='def5678', reason=redact('r'), at=MOMENT
        )
        for key, result in (results or {}).items()
    ]
    gate = create_gate_policy(run, decided, resolved)
    return ReviewReport(
        run=run, findings=tuple(findings), gate=gate, verdict=gate.verdict_of(findings)
    )


class TestStartedAndOverridden:
    def test_started_names_the_run_directory_and_models(self) -> None:
        view = render_started(create_run(), '.mightymodels/reviews/20260101-000001')

        assert view.text == (
            'run 20260101-000001 at .mightymodels/reviews/20260101-000001\n'
            'standard review: merge-vader on opus, uncle-bob on opus\n'
        )
        assert view.run_id == RUN
        assert view.verdict is None

    def test_overridden_names_the_heavier_reviewer_and_effort(self) -> None:
        view = render_overridden(create_run(), create_routing_table())

        assert view.text == (
            'run 20260101-000001: merge-vader on fable\ndispatch it with effort high\n'
        )
        assert view.run_id == RUN


class TestAdded:
    def test_added_lists_the_recorded_findings_and_the_reopened(self) -> None:
        added = AddedFindings(
            received=3,
            changed=(create_finding(1), create_finding(2)),
            reopened=('F2',),
            duplicates=(),
        )

        assert render_added(RUN, added).text == (
            '3 findings in, 2 recorded: F1, F2; back to undecided: F2\n'
        )

    def test_added_with_nothing_changed_says_none(self) -> None:
        added = AddedFindings(received=1, changed=(), reopened=(), duplicates=())

        assert render_added(RUN, added).text == '1 findings in, 0 recorded: none\n'

    def test_added_shows_a_near_duplicate_on_one_line(self) -> None:
        earlier = Match(
            kind='review-finding',
            reference='20251231-000001 F4',
            text=redact('first line\nsecond  line ' + 'x' * 200),
            overlap=0.876,
        )
        added = AddedFindings(
            received=1,
            changed=(create_finding(1),),
            reopened=(),
            duplicates=(Duplicate(written='20260101-000001 F1', earlier=earlier),),
        )

        lines = render_added(RUN, added).text.splitlines()

        assert lines[1].startswith(
            'near-duplicate: 20260101-000001 F1 resembles review-finding 20251231-000001 F4 '
            '(overlap 0.88): first line second line xxx'
        )
        assert lines[1].endswith('...')


class TestGate:
    def test_gate_orders_by_severity_then_security_then_weight(self) -> None:
        findings = [
            create_finding(1, severity='Medium'),
            create_finding(2, severity='High', source='UB'),
            create_finding(3, severity='High', source='MV'),
            create_finding(4, severity='High', source='UB', security=True),
            create_finding(5, severity='Critical'),
        ]

        view = render_gate(create_report(findings))

        assert [line.split('\t')[0] for line in view.text.splitlines()] == [
            'F5',
            'F4',
            'F3',
            'F2',
            'F1',
        ]
        assert view.run_id == RUN

    def test_gate_line_carries_label_sources_decision_and_conflict(self) -> None:
        finding = create_finding(
            7, security=True, kind='quality', source='UB', conflict='MV says Low'
        )

        view = render_gate(create_report([finding], decisions={'F7': 'defer'}))

        assert view.text == (
            'F7\tHigh security quality\t[UB-7]\tsrc/a.py:7\ttitle 7\tdefer\n'
            '\tconflict: MV says Low\n'
        )

    def test_undecided_finding_reads_undecided(self) -> None:
        assert render_gate(create_report([create_finding(1)])).text.endswith('\tundecided\n')

    def test_gate_without_findings_says_so(self) -> None:
        assert render_gate(create_report([])).text == 'no findings recorded\n'


class TestReport:
    def test_full_report_groups_findings_under_severities(self) -> None:
        findings = [
            create_finding(1, severity='Medium', conflict='UB says High'),
            create_finding(2, severity='High', with_evidence=True),
        ]
        report = create_report(findings, decisions={'F2': 'fix'}, results={'F2': 'failed'})

        view = render_report(report, 'full')

        assert view.verdict == 'BLOCK'
        assert view.text == (
            '# Review report\n\n'
            '**Verdict: BLOCK**\n\n'
            f'Review run `{RUN}` at `{HEAD[:12]}`: branch against main, standard depth, '
            'release-readiness emphasis. Reviewers: merge-vader (opus), uncle-bob (opus).\n\n'
            'Findings: 0 Critical, 1 High, 1 Medium, 0 Low.\n\n'
            '## High\n\n'
            '### F2 | High | title 2\n\n'
            '- Location: `src/a.py:2`\n'
            '- Sources: MV-2\n'
            '- Status: failed\n'
            '- Fix: fix 2\n'
            '- Verify: pytest -q\n'
            '- Evidence (metric): churn 9\n\n'
            '## Medium\n\n'
            '### F1 | Medium | title 1\n\n'
            '- Location: `src/a.py:1`\n'
            '- Sources: MV-1\n'
            '- Status: undecided\n'
            '- Fix: fix 1\n'
            '- Verify: pytest -q\n'
            '- Severity conflict: UB says High\n'
        )

    def test_full_report_names_the_scope_alone_without_a_base(self) -> None:
        report = create_report([])
        run = create_run(base=None)

        view = render_report(replace(report, run=run), 'full')

        assert ': branch, standard depth' in view.text
        assert view.verdict == 'CLEAR'

    def test_comment_report_leaves_out_low_findings(self) -> None:
        findings = [create_finding(1, severity='Low'), create_finding(2, severity='Medium')]

        view = render_report(create_report(findings), 'comment')

        assert view.verdict == 'MERGE WITH CONDITIONS'
        assert view.text.startswith('## Review\n\n**Verdict: MERGE WITH CONDITIONS**')
        assert view.text.endswith(
            'Findings: 0 Critical, 0 High, 1 Medium, 1 Low.\n\n'
            '- F2 (Medium, undecided): title 2. `src/a.py:2`\n'
        )

    def test_comment_report_caps_the_lines_and_counts_the_rest(self) -> None:
        findings = [create_finding(n, severity='Medium') for n in range(1, COMMENT_LIMIT + 4)]

        view = render_report(create_report(findings), 'comment')

        assert view.text.count('\n- F') == COMMENT_LIMIT
        assert view.text.endswith('- 3 more at Medium or above in the full report.\n')

    def test_comment_report_without_medium_findings_says_nothing_above(self) -> None:
        view = render_report(create_report([create_finding(1, severity='Low')]), 'comment')

        assert view.text.endswith('Nothing at Medium or above.\n')
        assert view.verdict == 'CLEAR'

    def test_fixed_result_clears_a_high_finding(self) -> None:
        report = create_report([create_finding(1)], results={'F1': 'fixed'})

        assert render_report(report, 'comment').verdict == 'CLEAR'


def create_summary(
    run_id: str, *, slug: Slug | None, findings: int, verdict: Verdict = 'CLEAR'
) -> RunSummary:
    run = create_run(slug=slug)
    return RunSummary(
        run=replace(run, run_id=RunId(run_id)),
        finding_count=findings,
        verdict=verdict,
    )


class TestListing:
    def test_listing_without_runs_says_so(self) -> None:
        view = render_listing(RunListing(runs=(), older_left_out=False), 50)

        assert view.text == NO_RUNS
        assert view.run_id is None

    def test_listing_shows_a_line_per_run(self) -> None:
        runs = (
            create_summary('20260101-000002', slug=Slug('probe'), findings=2, verdict='BLOCK'),
            create_summary('20260101-000001', slug=None, findings=0),
        )

        view = render_listing(RunListing(runs=runs, older_left_out=False), 50)

        assert view.text == (
            '20260101-000002\tprobe\tstandard\t2 findings\tBLOCK\n'
            '20260101-000001\t-\tstandard\t0 findings\tCLEAR\n'
        )

    def test_listing_says_when_older_runs_are_left_out(self) -> None:
        runs = (create_summary('20260101-000001', slug=None, findings=0),)

        view = render_listing(RunListing(runs=runs, older_left_out=True), 50)

        assert view.text.endswith('\nolder review runs are left out: these are the latest 50\n')
