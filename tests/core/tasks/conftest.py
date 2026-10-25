"""The database and service fixtures the task and attempt tests share."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract.records import Approval
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import TICKET_BY_SLUG, TicketSlugParams
from mightymodels_core.tasks import TaskReadService, TaskService
from mightymodels_core.tickets import SqliteTicketRepository

from tests.core.contract.fakes import ContractLedger, FakeContractRepository
from tests.core.primitives.clock import create_fake_clock
from tests.core.tasks.fakes import (
    FakeAttemptRepository,
    FakeTaskRepository,
    TaskLedger,
)
from tests.core.tickets.fakes import FakeTicketRepository

from .repository_builders import SQL, TICKET_SLUGS, create_ticket_section
from .service_builders import (
    BASE_COMMIT,
    COMMAND_KEY,
    OWNED_FILE,
    SERVICE_MOMENT,
    SERVICE_SLUG,
    ServiceHarness,
    create_command,
    create_receipt,
    create_start_request,
    verify_as_asked,
)

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
def staged_ticket_ids(database: Database) -> tuple[int, int]:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        tickets = SqliteTicketRepository(unit=unit, repository_id=repository.id)
        ids: list[int] = []
        for slug in TICKET_SLUGS:
            tickets.stage(slug, create_ticket_section(slug), ())
            row = unit.one(TICKET_BY_SLUG, TicketSlugParams(repository_id=repository.id, slug=slug))
            assert row is not None
            ids.append(row.id)
    first, second = ids
    return first, second


@pytest.fixture
def service_harness() -> ServiceHarness:
    tickets = FakeTicketRepository()
    record = tickets.stage(SERVICE_SLUG, create_ticket_section(SERVICE_SLUG), ())
    task_ledger = TaskLedger()
    contracts = FakeContractRepository(ledger=ContractLedger())
    clock = create_fake_clock(SERVICE_MOMENT)
    task_repository = FakeTaskRepository(ledger=task_ledger)
    attempts = FakeAttemptRepository(ledger=task_ledger)
    service = TaskService(
        tickets=tickets, tasks=task_repository, attempts=attempts, contracts=contracts, clock=clock
    )
    reads = TaskReadService(
        tickets=tickets, tasks=task_repository, attempts=attempts, contracts=contracts
    )
    return ServiceHarness(
        service=service,
        reads=reads,
        tickets=tickets,
        task_ledger=task_ledger,
        contracts=contracts,
        clock=clock,
        ticket_id=record.id,
    )


@pytest.fixture
def started_harness(service_harness: ServiceHarness) -> ServiceHarness:
    service_harness.service.start(SERVICE_SLUG, create_start_request())
    return service_harness


@pytest.fixture
def contracted_harness(started_harness: ServiceHarness) -> ServiceHarness:
    approval = Approval(at=SERVICE_MOMENT, head=BASE_COMMIT)
    started_harness.contracts.approve(
        started_harness.ticket_id, [create_command(COMMAND_KEY)], approval
    )
    return started_harness


@pytest.fixture
def proven_harness(contracted_harness: ServiceHarness) -> ServiceHarness:
    receipt = create_receipt(COMMAND_KEY)
    contracted_harness.contracts.record(contracted_harness.ticket_id, [receipt])
    return contracted_harness


@pytest.fixture
def verified_harness(proven_harness: ServiceHarness) -> ServiceHarness:
    verify_as_asked(proven_harness, frozenset({OWNED_FILE}))
    return proven_harness


@pytest.fixture
def foreign_command_harness(proven_harness: ServiceHarness) -> ServiceHarness:
    approval = Approval(at=SERVICE_MOMENT, head=BASE_COMMIT)
    proven_harness.contracts.approve(
        proven_harness.ticket_id, [create_command('T2.AC-1')], approval
    )
    return proven_harness
