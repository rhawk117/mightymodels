"""The service harnesses, the case record and the request and finding builders for services."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.reviews import IncomingFinding, ReviewService, StartRequest

from tests.core.primitives.clock import create_fake_clock
from tests.core.reviews.fakes import (
    FakeReviewDecisionRepository,
    FakeReviewRepository,
    ReviewLedger,
)
from tests.core.reviews.review_builders import SERVICE_MOMENT, create_finding
from tests.core.similarity.fakes import FakeSimilarityRepository

if TYPE_CHECKING:
    from collections.abc import Mapping

    from _pytest.mark import ParameterSet
    from mightymodels_core.primitives import Slug
    from mightymodels_core.reviews import FindingRecord, Persona, ReviewDecisionService
    from mightymodels_core.schemas.reviews import Depth, Emphasis, FindingSeverity, Scope


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceHarness:
    service: ReviewService
    reviews: FakeReviewRepository
    decisions: FakeReviewDecisionRepository
    similarity: FakeSimilarityRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class Case[Given, Expected]:
    name: str
    given: Given
    expected: Expected

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def create_request(
    *,
    scope: Scope = 'codebase',
    base: str | None = None,
    slug: Slug | None = None,
    depth: Depth = 'deep',
    emphasis: Emphasis = 'balanced',
    weights: Mapping[str, float] | None = None,
    persona: Persona | None = None,
) -> StartRequest:
    return StartRequest(
        scope=scope,
        base=base,
        slug=slug,
        depth=depth,
        emphasis=emphasis,
        weights=weights,
        persona=persona,
    )


def create_incoming(
    source: str, location: str = 'src/a.py:10', *, severity: FindingSeverity = 'High'
) -> IncomingFinding:
    return IncomingFinding(
        sources=(source,),
        severity=severity,
        kind='defect',
        security=False,
        title=f'{source} title',
        location=location,
        fix='fix it',
        verify='pytest -q',
        evidence=None,
    )


def create_gate_finding(
    key: str, source: str, severity: FindingSeverity = 'High', *, security: bool = False
) -> FindingRecord:
    return replace(create_finding(key), sources=(source,), severity=severity, security=security)


def create_service_harness() -> ServiceHarness:
    ledger = ReviewLedger()
    reviews = FakeReviewRepository(ledger=ledger)
    decisions = FakeReviewDecisionRepository(ledger=ledger)
    similarity = FakeSimilarityRepository()
    service = ReviewService(
        reviews=reviews,
        decisions=decisions,
        similarity=similarity,
        clock=create_fake_clock(SERVICE_MOMENT),
    )
    return ServiceHarness(
        service=service, reviews=reviews, decisions=decisions, similarity=similarity
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class DecisionHarness:
    service: ReviewDecisionService
    reviews: FakeReviewRepository
    decisions: FakeReviewDecisionRepository
