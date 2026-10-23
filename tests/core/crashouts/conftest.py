"""The crashout repository over a real sqlite unit and over the fake, one fixture for both."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.crashouts import (
    JOURNAL_WINDOW,
    CrashoutEntry,
    CrashoutRecord,
    CrashoutService,
    SqliteCrashoutRepository,
)
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import redact
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams

from tests.core.crashouts.fakes import FakeCrashoutRepository
from tests.core.primitives.clock import create_fake_clock
from tests.core.similarity.fakes import FakeSimilarityRepository

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.crashouts import (
        CrashoutRepository,
    )
    from mightymodels_core.database import Database

    from tests.core.primitives.clock import FakeClock

SQL = files('mightymodels_core.sql')
FIRST_AT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutHarness:
    crashouts: CrashoutRepository


def create_crashout(index: int = 0, *, branch: str | None = 'feat/retry') -> CrashoutRecord:
    return CrashoutRecord(
        at=FIRST_AT + timedelta(seconds=index),
        ticket_key='ENT-1',
        branch=None if branch is None else redact(branch),
        severity='heated',
        verdict='split',
        rant=redact(f'rant {index}'),
        failures=(redact('pytest failed'), redact('ruff failed')),
        root_cause=redact(f'root cause {index}'),
        corrective_action=redact('read the failing output first'),
        barked_back=False,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceHarness:
    service: CrashoutService
    crashouts: FakeCrashoutRepository
    similarity: FakeSimilarityRepository
    clock: FakeClock


def create_entry(
    *,
    rant: str = 'WHY did you skip the tests',
    failures: tuple[str, ...] = ('skipped the tests', 'claimed done'),
    root_cause: str = 'optimised for speed',
    corrective_action: str = 'run the gate before reporting',
    branch: str | None = 'fix/retry-queue',
) -> CrashoutEntry:
    return CrashoutEntry(
        ticket_key='retry-queue',
        branch=branch,
        severity='heated',
        verdict='deserved',
        rant=rant,
        failures=failures,
        root_cause=root_cause,
        corrective_action=corrective_action,
        barked_back=False,
    )


def crashout_implementation_cases() -> list[ParameterSet]:
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
def sqlite_harness(database: Database) -> Generator[CrashoutHarness]:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        yield CrashoutHarness(
            crashouts=SqliteCrashoutRepository(unit=unit, repository_id=repository.id)
        )


@pytest.fixture
def fake_harness() -> CrashoutHarness:
    return CrashoutHarness(crashouts=FakeCrashoutRepository())


@pytest.fixture(params=crashout_implementation_cases())
def harness(request: SubRequest) -> CrashoutHarness:
    return request.getfixturevalue(request.param)


@pytest.fixture
def journaled(harness: CrashoutHarness) -> CrashoutHarness:
    harness.crashouts.journal(create_crashout(0))
    harness.crashouts.journal(create_crashout(1))
    return harness


@pytest.fixture
def overfull(harness: CrashoutHarness) -> CrashoutHarness:
    for index in range(JOURNAL_WINDOW.rows + 1):
        harness.crashouts.journal(create_crashout(index))
    return harness


@pytest.fixture
def branchless(harness: CrashoutHarness) -> CrashoutHarness:
    harness.crashouts.journal(replace(create_crashout(0), branch=None))
    return harness


@pytest.fixture
def service_harness() -> ServiceHarness:
    crashouts = FakeCrashoutRepository()
    similarity = FakeSimilarityRepository()
    clock = create_fake_clock(MOMENT)
    service = CrashoutService(crashouts=crashouts, similarity=similarity, clock=clock)
    return ServiceHarness(service=service, crashouts=crashouts, similarity=similarity, clock=clock)


@pytest.fixture
def journaled_three(service_harness: ServiceHarness) -> ServiceHarness:
    first = create_entry(failures=('skipped the tests', 'claimed done'))
    second = replace(
        create_entry(failures=('skipped the tests again',)),
        severity='full-meltdown',
        barked_back=True,
        corrective_action='check the branch',
    )
    third = replace(
        create_entry(failures=('committed',), corrective_action='run the  gate before reporting'),
        verdict='split',
    )
    for day, entry in enumerate((first, second, third)):
        service_harness.clock.set_now(MOMENT + timedelta(days=day))
        service_harness.service.add(entry)
    return service_harness


@pytest.fixture
def overfull_service(service_harness: ServiceHarness) -> ServiceHarness:
    for _ in range(JOURNAL_WINDOW.rows + 1):
        service_harness.service.add(create_entry())
    return service_harness
