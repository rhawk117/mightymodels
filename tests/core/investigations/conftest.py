"""The investigation repository over a real sqlite unit and over the fake, one fixture for both."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.investigations import (
    InvestigationRecord,
    LedgerRecord,
    SqliteInvestigationRepository,
)
from mightymodels_core.investigations.tests.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.investigations import InvestigationRepository

SQL = files('mightymodels_core.sql')
FIRST = Slug('first-look')
SECOND = Slug('second-look')
UNADDED = Slug('never-added')


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationHarness:
    investigations: InvestigationRepository


def create_investigation(key: Slug) -> InvestigationRecord:
    return InvestigationRecord(key=key, target=redact(f'target of {key}'), kind='behavior')


def create_entry(seq: int, *, round_number: int = 1, day: int = 2) -> LedgerRecord:
    return LedgerRecord(
        seq=seq,
        round=round_number,
        kind='known',
        text=redact(f'entry {seq}'),
        source='code-scout',
        cite=redact(f'src/file.py:{seq}'),
        supersedes=(seq - 1,) if seq > 1 else (),
        at=datetime(2026, 1, day, 3, 4, 5, tzinfo=UTC),
        head='abc1234',
    )


def investigation_implementation_cases() -> list[ParameterSet]:
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
def repository_id(database: Database) -> int:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
    return repository.id


@pytest.fixture
def sqlite_harness(database: Database, repository_id: int) -> Generator[InvestigationHarness]:
    with database.write() as unit:
        yield InvestigationHarness(
            investigations=SqliteInvestigationRepository(unit=unit, repository_id=repository_id)
        )


@pytest.fixture
def fake_harness() -> InvestigationHarness:
    return InvestigationHarness(
        investigations=FakeInvestigationRepository(ledger=InvestigationLedger())
    )


@pytest.fixture(params=investigation_implementation_cases())
def harness(request: SubRequest) -> InvestigationHarness:
    return request.getfixturevalue(request.param)
