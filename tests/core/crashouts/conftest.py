"""The fixtures the crashout tests share; each tier conftest supplies the `harness`."""

from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.crashouts import JOURNAL_WINDOW, CrashoutService
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS

from tests.core.crashouts.crashout_builders import (
    MOMENT,
    SQL,
    ServiceHarness,
    create_crashout,
    create_entry,
)
from tests.core.crashouts.fakes import FakeCrashoutRepository
from tests.core.primitives.clock import create_fake_clock
from tests.core.similarity.fakes import FakeSimilarityRepository

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database

    from tests.core.crashouts.crashout_builders import CrashoutHarness


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
