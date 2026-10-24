"""The run, finding, decision and outcome builders and the shared ids of the review tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

from mightymodels_core.primitives import RunId, Slug, redact
from mightymodels_core.reviews import (
    DecidedFinding,
    Evidence,
    FindingRecord,
    ResolvedFinding,
    ReviewRunRecord,
)

if TYPE_CHECKING:
    from mightymodels_core.reviews import ReviewDecisionRepository, ReviewRepository
    from mightymodels_core.schemas.reviews import Decision, Result

SQL = files('mightymodels_core.sql')
FIRST_RUN = RunId('20260101-000001')
SECOND_RUN = RunId('20260101-000002')
UNSTARTED_RUN = RunId('20260101-000009')
SLUG = Slug('review-subject')
OTHER_SLUG = Slug('other-subject')
SERVICE_MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
SERVICE_RUN = RunId('20260506-070809')
HEAD = 'abc1234'


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewHarness:
    reviews: ReviewRepository
    decisions: ReviewDecisionRepository


def create_run(run_id: RunId = FIRST_RUN, *, slug: Slug | None = SLUG) -> ReviewRunRecord:
    return ReviewRunRecord(
        run_id=run_id,
        slug=slug,
        scope='branch',
        base='main',
        head='abc1234',
        depth='standard',
        emphasis='balanced',
        weights={'merge-vader': 0.5, 'uncle-bob': 0.5},
        personas=('merge-vader', 'uncle-bob'),
        models={'merge-vader': 'opus', 'uncle-bob': None},
        created_at=datetime(2026, 1, 1, 3, 4, 5, tzinfo=UTC),
    )


def create_finding(
    key: str, *, title: str = 'a defect', with_evidence: bool = True
) -> FindingRecord:
    return FindingRecord(
        key=key,
        sources=('merge-vader',),
        severity='High',
        kind='defect',
        security=False,
        title=redact(title),
        location=redact('src/a.py:10'),
        fix=redact('fix it'),
        verify=redact('pytest -q'),
        evidence=Evidence(kind='metric', cite=redact('churn 9')) if with_evidence else None,
        conflict=None if with_evidence else redact('the other reviewer disagrees'),
    )


def create_decided(key: str, *, decision: Decision = 'fix') -> DecidedFinding:
    return DecidedFinding(
        finding_key=key,
        decision=decision,
        reason=redact('worth doing'),
        by=redact('owner'),
        at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


def create_resolved(key: str, *, result: Result = 'fixed') -> ResolvedFinding:
    return ResolvedFinding(
        finding_key=key,
        result=result,
        commit='def5678',
        reason=redact('done'),
        at=datetime(2026, 1, 3, 3, 4, 5, tzinfo=UTC),
    )
