"""What the review tools return, and the short texts.

The short texts are started, overridden, added, listed, disposed and resolved. Each function
takes core's results and returns text, so no git, file or unit of work is read here.
"""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import short_head
from mightymodels_core.reviews import OverridePolicy, Verdict
from pydantic import BaseModel, ConfigDict

from mightymodels_mcp.server.views import duplicates_text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import RoutingTable
    from mightymodels_core.reviews import (
        AddedFindings,
        Disposed,
        FindingRecord,
        GatePolicy,
        ResolvedFinding,
        ReviewReport,
        ReviewRunRecord,
        RunListing,
    )
    from mightymodels_core.vocabulary.reviews import StoredSeverity

    from mightymodels_mcp.review.schemas import ReportShape

COMMENT_LIMIT = 10
UNDECIDED = 'undecided'
NO_FINDINGS = 'no findings recorded\n'
SEVERITIES: tuple[StoredSeverity, ...] = ('Critical', 'High', 'Medium', 'Low')
NO_RUNS = 'no review runs\n'
NO_SLUG = '-'


class ReviewView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    run_id: str | None = None
    verdict: Verdict | None = None


def render_started(run: ReviewRunRecord, relative: str) -> ReviewView:
    listed = ', '.join(f'{name} on {model}' for name, model in run.models.items())
    text = f'run {run.run_id} at {relative}\n{run.depth} review: {listed}\n'
    return ReviewView(text=text, run_id=run.run_id)


def render_overridden(run: ReviewRunRecord, routing: RoutingTable) -> ReviewView:
    reviewer = OverridePolicy(run=run, routing=routing).heavier_persona
    model = routing.override_model
    text = (
        f'run {run.run_id}: {reviewer} on {model}\n'
        f'dispatch it with effort {routing.effort_of(model)}\n'
    )
    return ReviewView(text=text, run_id=run.run_id)


def render_added(run_id: str, added: AddedFindings) -> ReviewView:
    ids = ', '.join(finding.key for finding in added.changed) or 'none'
    tail = f'; back to undecided: {", ".join(added.reopened)}' if added.reopened else ''
    text = (
        f'{added.received} findings in, {len(added.changed)} recorded: {ids}{tail}\n'
        f'{duplicates_text(added.duplicates)}'
    )
    return ReviewView(text=text, run_id=run_id)


def render_disposed(run_id: str, disposed: Disposed) -> ReviewView:
    tail = f'; undecided: {", ".join(disposed.undecided)}' if disposed.undecided else ''
    return ReviewView(text=f'{disposed.recorded} dispositions recorded{tail}\n', run_id=run_id)


def render_resolved(run_id: str, resolved: ResolvedFinding) -> ReviewView:
    return ReviewView(text=f'{resolved.finding_key} {resolved.result}\n', run_id=run_id)


def render_listing(listing: RunListing, kept: int) -> ReviewView:
    lines = (
        f'{summary.run.run_id}\t{summary.run.slug or NO_SLUG}\t{summary.run.depth}\t'
        f'{summary.finding_count} findings\t{summary.verdict}\n'
        for summary in listing.runs
    )
    note = (
        f'older review runs are left out: these are the latest {kept}\n'
        if listing.older_left_out
        else ''
    )
    return ReviewView(text=(''.join(lines) or NO_RUNS) + note)


def decision_text(finding: FindingRecord, gate: GatePolicy) -> str:
    return gate.decision_of(finding) or UNDECIDED


def status_text(finding: FindingRecord, gate: GatePolicy) -> str:
    return gate.results.get(finding.key) or decision_text(finding, gate)


def label(finding: FindingRecord) -> str:
    tags = [finding.severity]
    if finding.security:
        tags.append('security')

    if finding.kind == 'quality':
        tags.append('quality')

    return ' '.join(tags)


def gate_line(finding: FindingRecord, gate: GatePolicy) -> str:
    sources = '/'.join(finding.sources)
    line = (
        f'{finding.key}\t{label(finding)}\t[{sources}]\t{finding.location}\t'
        f'{finding.title}\t{decision_text(finding, gate)}\n'
    )
    if finding.conflict is None:
        return line

    return f'{line}\tconflict: {finding.conflict}\n'


def render_gate(report: ReviewReport) -> ReviewView:
    ordered = report.gate.ordered(report.findings)
    text = ''.join(gate_line(finding, report.gate) for finding in ordered) or NO_FINDINGS
    return ReviewView(text=text, run_id=report.run.run_id)


def counts(findings: Sequence[FindingRecord]) -> str:
    tally = (
        f'{sum(1 for finding in findings if finding.severity == severity)} {severity}'
        for severity in SEVERITIES
    )
    return ', '.join(tally)


def header_lines(
    run: ReviewRunRecord, findings: Sequence[FindingRecord], verdict: Verdict
) -> list[str]:
    scope = run.scope if run.base is None else f'{run.scope} against {run.base}'
    models = ', '.join(f'{name} ({model})' for name, model in run.models.items())
    return [
        f'**Verdict: {verdict}**',
        '',
        (
            f'Review run `{run.run_id}` at `{short_head(run.head)}`: '
            f'{scope}, {run.depth} depth, {run.emphasis} emphasis. Reviewers: {models}.'
        ),
        '',
        f'Findings: {counts(findings)}.',
    ]


def finding_block(finding: FindingRecord, gate: GatePolicy) -> list[str]:
    lines = [
        f'### {finding.key} | {label(finding)} | {finding.title}',
        '',
        f'- Location: `{finding.location}`',
        f'- Sources: {", ".join(finding.sources)}',
        f'- Status: {status_text(finding, gate)}',
        f'- Fix: {finding.fix}',
        f'- Verify: {finding.verify}',
    ]
    if finding.evidence is not None:
        lines.append(f'- Evidence ({finding.evidence.kind}): {finding.evidence.cite}')

    if finding.conflict is not None:
        lines.append(f'- Severity conflict: {finding.conflict}')

    return [*lines, '']


def severity_section(
    severity: StoredSeverity, findings: Sequence[FindingRecord], gate: GatePolicy
) -> list[str]:
    group = [finding for finding in findings if finding.severity == severity]
    if not group:
        return []

    blocks = (line for finding in group for line in finding_block(finding, gate))
    return [f'## {severity}', '', *blocks]


def full_report(report: ReviewReport, findings: Sequence[FindingRecord]) -> str:
    lines = ['# Review report', '', *header_lines(report.run, findings, report.verdict), '']
    for severity in SEVERITIES:
        lines.extend(severity_section(severity, findings, report.gate))

    return '\n'.join(lines).rstrip() + '\n'


def comment_line(finding: FindingRecord, gate: GatePolicy) -> str:
    return (
        f'- {finding.key} ({label(finding)}, {status_text(finding, gate)}): {finding.title}. '
        f'`{finding.location}`'
    )


def comment_report(report: ReviewReport, findings: Sequence[FindingRecord]) -> str:
    shown = [finding for finding in findings if finding.severity != 'Low']
    lines = ['## Review', '', *header_lines(report.run, findings, report.verdict), '']
    lines.extend(comment_line(finding, report.gate) for finding in shown[:COMMENT_LIMIT])
    hidden = len(shown) - COMMENT_LIMIT
    if hidden > 0:
        lines.append(f'- {hidden} more at Medium or above in the full report.')

    if not shown:
        lines.append('Nothing at Medium or above.')

    return '\n'.join(lines).rstrip() + '\n'


def render_report(report: ReviewReport, shape: ReportShape) -> ReviewView:
    ordered = report.gate.ordered(report.findings)
    text = (full_report if shape == 'full' else comment_report)(report, ordered)
    return ReviewView(text=text, run_id=report.run.run_id, verdict=report.verdict)
