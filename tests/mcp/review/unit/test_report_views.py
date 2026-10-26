from dataclasses import replace

from mightymodels_mcp.review.views import COMMENT_LIMIT, render_gate, render_report

from tests.mcp.review.review_builders import (
    HEAD,
    RUN,
    create_finding,
    create_report,
    create_run,
)


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
