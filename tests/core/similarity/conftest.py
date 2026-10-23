"""The similarity repositories over a real sqlite unit and over the fakes, one fixture for both."""

from dataclasses import dataclass
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import redact
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.similarity import (
    ScoutReport,
    SqliteScoutReportRepository,
    SqliteSimilarityRepository,
    Written,
)

from tests.core.similarity.fakes import (
    FakeScoutReportRepository,
    FakeSimilarityRepository,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.schemas.scout_reports import Scout
    from mightymodels_core.schemas.similarity import SimilarityKind
    from mightymodels_core.similarity import ScoutReportRepository, SimilarityRepository

SQL = files('mightymodels_core.sql')
STORED_TEXT = 'the retry loop drops the connection pool after a timeout'
STORED_REFERENCE = 'ENT-1'
STORED_TARGET = 'src/api/client.py'


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityHarness:
    similarity: SimilarityRepository
    scouts: ScoutReportRepository


def create_written(reference: str, text: str, *, kind: SimilarityKind = 'ledger-entry') -> Written:
    return Written(kind=kind, reference=reference, text=redact(text))


def create_scout_report(
    target: str = STORED_TARGET, *, scout: Scout = 'code-scout', report: str = 'it is async'
) -> ScoutReport:
    return ScoutReport(scout=scout, target=redact(target), report=redact(report))


def similarity_implementation_cases() -> list[ParameterSet]:
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
def sqlite_harness(database: Database) -> Generator[SimilarityHarness]:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        yield SimilarityHarness(
            similarity=SqliteSimilarityRepository(unit=unit, repository_id=repository.id),
            scouts=SqliteScoutReportRepository(unit=unit, repository_id=repository.id),
        )


@pytest.fixture
def fake_harness() -> SimilarityHarness:
    return SimilarityHarness(
        similarity=FakeSimilarityRepository(), scouts=FakeScoutReportRepository()
    )


@pytest.fixture(params=similarity_implementation_cases())
def harness(request: SubRequest) -> SimilarityHarness:
    return request.getfixturevalue(request.param)


@pytest.fixture
def stocked(harness: SimilarityHarness) -> SimilarityHarness:
    harness.similarity.record(create_written(STORED_REFERENCE, STORED_TEXT))
    harness.scouts.add_report(create_scout_report())
    return harness
