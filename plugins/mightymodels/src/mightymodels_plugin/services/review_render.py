"""What a review run says: the gate order, the verdict and the two report texts.

Weights order findings inside a severity; they never filter or downgrade one. The verdict is
computed from the findings, the user's dispositions and the remediation outcomes, never written.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from mightymodels_plugin.db.tables import ReviewDispositionRow, ReviewOutcomeRow, ReviewRunRow
from mightymodels_plugin.models.review import (
    Decision,
    Finding,
    Kind,
    Result,
    Severity,
    Shape,
    Verdict,
)
from mightymodels_plugin.services.review_findings import RANK, number_of

COMMENT_LIMIT = 10
SHORT_SHA = 12
UNDECIDED = 'undecided'
CLOSED_BY_DECISION = frozenset({Decision.DISMISS})
SOURCE_PERSONA: Mapping[str, str] = MappingProxyType({'MV': 'merge-vader', 'UB': 'uncle-bob'})

type Renderer = Callable[[Standing, Sequence[Finding]], str]


@dataclass(slots=True, kw_only=True, frozen=True)
class Standing:
    run: ReviewRunRow
    dispositions: Mapping[str, ReviewDispositionRow]
    outcomes: Mapping[str, ReviewOutcomeRow]


def heaviest_weight(finding: Finding, standing: Standing) -> float:
    weights = standing.run.weights
    return max(weights.get(SOURCE_PERSONA[source.split('-')[0]], 0) for source in finding.sources)


@dataclass(frozen=True, slots=True)
class GateOrder:
    standing: Standing

    def __call__(self, finding: Finding) -> tuple[int, bool, float, int]:
        return (
            RANK[finding.severity],
            not finding.security,
            -heaviest_weight(finding, self.standing),
            number_of(finding),
        )


def ordered(findings: Sequence[Finding], standing: Standing) -> list[Finding]:
    return sorted(findings, key=GateOrder(standing))


def decision_of(finding: Finding, standing: Standing) -> str:
    disposition = standing.dispositions.get(finding.id)
    return disposition.decision if disposition else UNDECIDED


def label(finding: Finding) -> str:
    tags = [str(finding.severity)]
    if finding.security:
        tags.append('security')
    if finding.kind is Kind.QUALITY:
        tags.append('quality')
    return ' '.join(tags)


def gate_line(finding: Finding, standing: Standing) -> str:
    sources = '/'.join(finding.sources)
    line = (
        f'{finding.id}\t{label(finding)}\t[{sources}]\t{finding.location}\t'
        f'{finding.title}\t{decision_of(finding, standing)}\n'
    )
    if finding.conflict:
        line += f'\tconflict: {finding.conflict}\n'
    return line


def gate_text(findings: Sequence[Finding], standing: Standing) -> str:
    if not findings:
        return 'no findings recorded\n'
    return ''.join(gate_line(finding, standing) for finding in ordered(findings, standing))


def is_open(finding: Finding, standing: Standing) -> bool:
    outcome = standing.outcomes.get(finding.id)
    fixed = outcome is not None and outcome.result == Result.FIXED
    return not fixed and decision_of(finding, standing) not in CLOSED_BY_DECISION


def is_blocking(finding: Finding, standing: Standing) -> bool:
    if finding.severity is Severity.CRITICAL:
        return True
    return (
        finding.severity is Severity.HIGH and decision_of(finding, standing) != Decision.ACCEPT_RISK
    )


def verdict_of(findings: Sequence[Finding], standing: Standing) -> Verdict:
    remaining = [finding for finding in findings if is_open(finding, standing)]
    if any(is_blocking(finding, standing) for finding in remaining):
        return Verdict.BLOCK
    if any(RANK[finding.severity] <= RANK[Severity.MEDIUM] for finding in remaining):
        return Verdict.CONDITIONS
    return Verdict.CLEAR


def status_of(finding: Finding, standing: Standing) -> str:
    outcome = standing.outcomes.get(finding.id)
    return outcome.result if outcome else decision_of(finding, standing)


def counts(findings: Sequence[Finding]) -> str:
    tally = [
        f'{sum(1 for finding in findings if finding.severity is severity)} {severity}'
        for severity in Severity
    ]
    return ', '.join(tally)


def header_lines(findings: Sequence[Finding], standing: Standing) -> list[str]:
    run = standing.run
    scope = f'{run.scope} against {run.base}' if run.base else run.scope
    models = ', '.join(f'{name} ({model})' for name, model in run.models.items())
    return [
        f'**Verdict: {verdict_of(findings, standing)}**',
        '',
        (
            f'Review run `{run.run_id}` at `{(run.head or "unknown")[:SHORT_SHA]}`: '
            f'{scope}, {run.depth} depth, {run.emphasis} emphasis. Reviewers: {models}.'
        ),
        '',
        f'Findings: {counts(findings)}.',
    ]


def finding_block(finding: Finding, standing: Standing) -> list[str]:
    lines = [
        f'### {finding.id} | {label(finding)} | {finding.title}',
        '',
        f'- Location: `{finding.location}`',
        f'- Sources: {", ".join(finding.sources)}',
        f'- Status: {status_of(finding, standing)}',
        f'- Fix: {finding.fix}',
        f'- Verify: {finding.verify}',
    ]
    if finding.evidence:
        lines.append(f'- Evidence ({finding.evidence.kind}): {finding.evidence.cite}')
    if finding.conflict:
        lines.append(f'- Severity conflict: {finding.conflict}')
    disposition = standing.dispositions.get(finding.id)
    if disposition and disposition.reason:
        lines.append(f'- Decision reason: {disposition.reason}')
    return [*lines, '']


def severity_section(
    severity: Severity, findings: Sequence[Finding], standing: Standing
) -> list[str]:
    group = [finding for finding in findings if finding.severity is severity]
    if not group:
        return []
    blocks = (line for finding in group for line in finding_block(finding, standing))
    return [f'## {severity}', '', *blocks]


def full_report(standing: Standing, findings: Sequence[Finding]) -> str:
    lines = ['# Review report', '', *header_lines(findings, standing), '']
    for severity in Severity:
        lines.extend(severity_section(severity, findings, standing))
    return '\n'.join(lines).rstrip() + '\n'


def comment_line(finding: Finding, standing: Standing) -> str:
    return (
        f'- {finding.id} ({label(finding)}, {status_of(finding, standing)}): {finding.title}. '
        f'`{finding.location}`'
    )


def comment_report(standing: Standing, findings: Sequence[Finding]) -> str:
    shown = [finding for finding in findings if finding.severity is not Severity.LOW]
    lines = ['## Review', '', *header_lines(findings, standing), '']
    lines.extend(comment_line(finding, standing) for finding in shown[:COMMENT_LIMIT])
    hidden = len(shown) - COMMENT_LIMIT
    if hidden > 0:
        lines.append(f'- {hidden} more at Medium or above in the full report.')
    if not shown:
        lines.append('Nothing at Medium or above.')
    return '\n'.join(lines).rstrip() + '\n'


RENDERERS: Mapping[Shape, Renderer] = MappingProxyType(
    {Shape.FULL: full_report, Shape.COMMENT: comment_report}
)


def report_text(shape: Shape, findings: Sequence[Finding], standing: Standing) -> str:
    return RENDERERS[shape](standing, ordered(findings, standing))
