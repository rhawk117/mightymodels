"""The review view tests' shared builders: a run, findings, a report and a run summary."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.primitives import RunId, redact
from mightymodels_core.reviews import (
    Evidence,
    FindingRecord,
    ReviewReport,
    ReviewRunRecord,
    create_gate_policy,
)
from mightymodels_core.reviews.records import DecidedFinding, ResolvedFinding
from mightymodels_core.reviews.services import RunSummary

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import Slug
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


def create_summary(
    run_id: str, *, slug: Slug | None, findings: int, verdict: Verdict = 'CLEAR'
) -> RunSummary:
    run = create_run(slug=slug)
    return RunSummary(
        run=replace(run, run_id=RunId(run_id)),
        finding_count=findings,
        verdict=verdict,
    )
