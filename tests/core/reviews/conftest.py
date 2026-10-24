"""The review repositories over a real sqlite unit and over the fakes, one fixture for both."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.reviews import (
    ReviewDecisionService,
    SqliteReviewDecisionRepository,
    SqliteReviewRepository,
)
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams

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
    SQL,
    ReviewHarness,
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
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database

    from tests.core.reviews.service_builders import ServiceHarness


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
