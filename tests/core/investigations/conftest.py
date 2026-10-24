"""The fixtures the investigation tests share; each tier conftest supplies the `harness`."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.investigations import InvestigationService
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams

from tests.core.investigations.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from tests.core.investigations.investigation_builders import (
    MOMENT,
    SQL,
    InvestigationHarness,
    ServiceHarness,
)
from tests.core.primitives.clock import create_fake_clock
from tests.core.similarity.fakes import FakeSimilarityRepository

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database


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
def repository_id(database: Database) -> int:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
    return repository.id


@pytest.fixture
def fake_harness() -> InvestigationHarness:
    return InvestigationHarness(
        investigations=FakeInvestigationRepository(ledger=InvestigationLedger())
    )


@pytest.fixture
def service_harness() -> ServiceHarness:
    investigations = FakeInvestigationRepository(ledger=InvestigationLedger())
    similarity = FakeSimilarityRepository()
    clock = create_fake_clock(MOMENT)
    service = InvestigationService(
        investigations=investigations, similarity=similarity, clock=clock
    )
    return ServiceHarness(
        service=service, investigations=investigations, similarity=similarity, clock=clock
    )
