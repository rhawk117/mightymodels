"""The contract repository over a real sqlite unit and over the fake, one fixture for both."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import (
    Approval,
    ApprovedCommand,
    ContractService,
    Receipt,
    SqliteContractRepository,
)
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.primitives.tests.clock import create_fake_clock
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import TICKET_BY_SLUG, TicketSlugParams
from mightymodels_core.tickets import SqliteTicketRepository, TicketSection, Tracker
from mightymodels_core.tickets.tests.fakes import FakeTicketRepository

from tests.core.contract.fakes import ContractLedger, FakeContractRepository

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.contract import ContractRepository
    from mightymodels_core.database import Database
    from mightymodels_core.schemas.contract import Outcome

SQL = files('mightymodels_core.sql')
TICKET_SLUGS = (Slug('contract-subject'), Slug('other-subject'))
FAKE_TICKET_IDS = (1, 2)
APPROVAL = Approval(at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC), head='abc1234')
SERVICE_SLUG = Slug('service-subject')
SERVICE_MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
HEAD = 'abc1234'
FIRST_KEY = 'T1.AC-1'
SECOND_KEY = 'T1.AC-2'


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractHarness:
    contract: ContractRepository
    ticket_id: int
    other_ticket_id: int


def create_command(key: str, *, argv: tuple[str, ...] = ('make', 'test')) -> ApprovedCommand:
    return ApprovedCommand(key=key, argv=argv, expect_exit=0, timeout=300, approved_by='planner')


def create_receipt(key: str, outcome: Outcome = 'pass', *, day: int = 3) -> Receipt:
    return Receipt(
        key=key,
        argv=('make', 'test'),
        outcome=outcome,
        exit=0 if outcome == 'pass' else 1,
        duration_ms=120,
        stdout_tail=redact('ok'),
        stderr_tail=redact(''),
        digest='d1',
        head='abc1234',
        phase='task',
        at=datetime(2026, 1, day, 3, 4, 5, tzinfo=UTC),
    )


def create_ticket_section(slug: Slug) -> TicketSection:
    return TicketSection(
        ticket=f'.mightymodels/{slug}/ticket.yml',
        summary=redact('a summary'),
        branch='main',
        scope='med',
        plan_first=False,
        auto_escalate=False,
        models={'engineer': 'sonnet'},
        tracker=Tracker(issue=None, jira=None),
        context=(),
        validated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceHarness:
    service: ContractService
    ledger: ContractLedger
    contracts: FakeContractRepository
    ticket_id: int


def create_service_harness() -> ServiceHarness:
    ledger = ContractLedger()
    contracts = FakeContractRepository(ledger=ledger)
    tickets = FakeTicketRepository()
    ticket_id = tickets.stage(SERVICE_SLUG, create_ticket_section(SERVICE_SLUG), ()).id
    service = ContractService(
        tickets=tickets, contracts=contracts, clock=create_fake_clock(SERVICE_MOMENT)
    )
    return ServiceHarness(service=service, ledger=ledger, contracts=contracts, ticket_id=ticket_id)


def contract_implementation_cases() -> list[ParameterSet]:
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
def sqlite_harness(
    database: Database, staged_ticket_ids: tuple[int, int]
) -> Generator[ContractHarness]:
    ticket_id, other_ticket_id = staged_ticket_ids
    with database.write() as unit:
        yield ContractHarness(
            contract=SqliteContractRepository(unit=unit),
            ticket_id=ticket_id,
            other_ticket_id=other_ticket_id,
        )


@pytest.fixture
def fake_harness() -> ContractHarness:
    ticket_id, other_ticket_id = FAKE_TICKET_IDS
    return ContractHarness(
        contract=FakeContractRepository(ledger=ContractLedger()),
        ticket_id=ticket_id,
        other_ticket_id=other_ticket_id,
    )


@pytest.fixture(params=contract_implementation_cases())
def harness(request: SubRequest) -> ContractHarness:
    return request.getfixturevalue(request.param)


@pytest.fixture
def service_harness() -> ServiceHarness:
    return create_service_harness()


@pytest.fixture
def stocked_service_harness(service_harness: ServiceHarness) -> ServiceHarness:
    commands = [create_command(FIRST_KEY), create_command(SECOND_KEY)]
    service_harness.contracts.approve(service_harness.ticket_id, commands, APPROVAL)
    return service_harness
