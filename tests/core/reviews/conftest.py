"""The service fixtures the review tests share."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.reviews import ReviewDecisionService

from tests.core.primitives.clock import create_fake_clock
from tests.core.reviews.fakes import (
    FakeReviewDecisionRepository,
    FakeReviewRepository,
    ReviewLedger,
)
from tests.core.reviews.review_builders import (
    FIRST_RUN,
    HEAD,
    SERVICE_MOMENT,
    create_decided,
    create_finding,
    create_run,
)
from tests.core.reviews.service_builders import (
    DecisionHarness,
    create_request,
    create_service_harness,
)

if TYPE_CHECKING:
    from tests.core.reviews.service_builders import ServiceHarness


@pytest.fixture
def service_harness() -> ServiceHarness:
    return create_service_harness()


@pytest.fixture
def started_harness(service_harness: ServiceHarness) -> ServiceHarness:
    service_harness.service.start(create_request(emphasis='release-readiness'), HEAD)
    return service_harness


@pytest.fixture
def decision_harness() -> DecisionHarness:
    ledger = ReviewLedger()
    reviews = FakeReviewRepository(ledger=ledger)
    decisions = FakeReviewDecisionRepository(ledger=ledger)
    clock = create_fake_clock(SERVICE_MOMENT)
    reviews.record_run(create_run(FIRST_RUN))
    reviews.record_findings(FIRST_RUN, [create_finding(f'MV-{number}') for number in (1, 2, 3)])
    service = ReviewDecisionService(reviews=reviews, decisions=decisions, clock=clock)
    return DecisionHarness(service=service, reviews=reviews, decisions=decisions)


@pytest.fixture
def chosen_harness(decision_harness: DecisionHarness) -> DecisionHarness:
    decided = [create_decided('MV-1', decision='fix'), create_decided('MV-2', decision='defer')]
    decision_harness.decisions.record_dispositions(FIRST_RUN, decided)
    return decision_harness
