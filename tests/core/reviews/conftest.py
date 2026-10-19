"""The review repositories over a real sqlite unit and over the fakes, one fixture for both."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import RunId, Slug, redact
from mightymodels_core.reviews import (
    DecidedFinding,
    Evidence,
    FindingRecord,
    ResolvedFinding,
    ReviewRunRecord,
    SqliteReviewDecisionRepository,
    SqliteReviewRepository,
)
from mightymodels_core.reviews.tests.fakes import (
    FakeReviewDecisionRepository,
    FakeReviewRepository,
    ReviewLedger,
)
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.reviews import ReviewDecisionRepository, ReviewRepository
    from mightymodels_core.schemas.reviews import Decision, Result

SQL = files('mightymodels_core.sql')
FIRST_RUN = RunId('20260101-000001')
SECOND_RUN = RunId('20260101-000002')
UNSTARTED_RUN = RunId('20260101-000009')
SLUG = Slug('review-subject')
OTHER_SLUG = Slug('other-subject')


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


def review_implementation_cases() -> list[ParameterSet]:
    return [
        pytest.param('sqlite_harness', id='sqlite', marks=pytest.mark.integration),
        pytest.param('fake_harness', id='fake'),
    ]


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path.joinpath('mightymodels.db')


@pytest.fixture
def database_spec() -> DatabaseSpec:
    return DatabaseSpec(
        schema=SQL.joinpath('schema.sql'),
        statements=SQL.joinpath('statements.sql'),
        declarations=DECLARATIONS,
    )


@pytest.fixture
def database(database_path: Path, database_spec: DatabaseSpec) -> Generator[Database]:
    opened = open_database(database_path, database_spec, ConnectionOptions())
    yield opened
    opened.close()


@pytest.fixture
def sqlite_harness(database: Database) -> Generator[ReviewHarness]:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        yield ReviewHarness(
            reviews=SqliteReviewRepository(unit=unit, repository_id=repository.id),
            decisions=SqliteReviewDecisionRepository(unit=unit, repository_id=repository.id),
        )


@pytest.fixture
def fake_harness() -> ReviewHarness:
    ledger = ReviewLedger()
    return ReviewHarness(
        reviews=FakeReviewRepository(ledger=ledger),
        decisions=FakeReviewDecisionRepository(ledger=ledger),
    )


@pytest.fixture(params=review_implementation_cases())
def harness(request: SubRequest) -> ReviewHarness:
    return request.getfixturevalue(request.param)
