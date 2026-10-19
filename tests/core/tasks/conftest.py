"""The task and attempt repositories over a real sqlite unit and over the fakes."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract.records import Approval, ApprovedCommand, Receipt
from mightymodels_core.contract.tests.fakes import ContractLedger, FakeContractRepository
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import Slug, TaskId, redact
from mightymodels_core.primitives.tests.clock import create_fake_clock
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import TICKET_BY_SLUG, TicketSlugParams
from mightymodels_core.tasks import (
    Attempt,
    Brief,
    GitFacts,
    SqliteAttemptRepository,
    SqliteTaskRepository,
    StartRequest,
    TaskService,
    Transition,
    VerifyRequest,
)
from mightymodels_core.tasks.tests.fakes import (
    FakeAttemptRepository,
    FakeTaskRepository,
    TaskLedger,
)
from mightymodels_core.tickets import SqliteTicketRepository, TicketSection, Tracker
from mightymodels_core.tickets.tests.fakes import FakeTicketRepository

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.primitives.tests.clock import FakeClock
    from mightymodels_core.schemas.tasks import ArchitectMode, TaskStatus, Worker
    from mightymodels_core.tasks import AttemptRepository, TaskRecord, TaskRepository

SQL = files('mightymodels_core.sql')
TICKET_SLUGS = (Slug('tasks-subject'), Slug('other-subject'))
FAKE_TICKET_IDS = (1, 2)
FIRST_TASK = TaskId('T1')
SECOND_TASK = TaskId('T2')
SERVICE_SLUG = Slug('service-subject')
SERVICE_MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
BASE_COMMIT = 'base001'
DONE_COMMIT = 'abc1234'
OWNED_FILE = 'src/a.py'
COMMAND_KEY = 'T1.AC-1'
BRIEF_TEXT = f'## ASKED\nacceptance:\n  - AC-1: it works\n## DONE\ncommit: {DONE_COMMIT}\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskHarness:
    tasks: TaskRepository
    attempts: AttemptRepository
    ticket_id: int
    other_ticket_id: int


def create_transition(
    task_key: TaskId,
    before: TaskStatus,
    after: TaskStatus,
    *,
    day: int = 2,
    head: str | None = 'abc1234',
    reasons: tuple[str, ...] = (),
) -> Transition:
    return Transition(
        task_key=task_key,
        before=before,
        after=after,
        reasons=tuple(redact(reason) for reason in reasons),
        head=head,
        at=datetime(2026, 1, day, 3, 4, 5, tzinfo=UTC),
    )


def create_attempt(*, owned: tuple[str, ...] = ('src/a.py',)) -> Attempt:
    return Attempt(worker='engineer', mode=None, owned=owned)


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


def task_implementation_cases() -> list[ParameterSet]:
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
) -> Generator[TaskHarness]:
    ticket_id, other_ticket_id = staged_ticket_ids
    with database.write() as unit:
        yield TaskHarness(
            tasks=SqliteTaskRepository(unit=unit),
            attempts=SqliteAttemptRepository(unit=unit),
            ticket_id=ticket_id,
            other_ticket_id=other_ticket_id,
        )


@pytest.fixture
def fake_harness() -> TaskHarness:
    ledger = TaskLedger()
    ticket_id, other_ticket_id = FAKE_TICKET_IDS
    return TaskHarness(
        tasks=FakeTaskRepository(ledger=ledger),
        attempts=FakeAttemptRepository(ledger=ledger),
        ticket_id=ticket_id,
        other_ticket_id=other_ticket_id,
    )


@pytest.fixture(params=task_implementation_cases())
def harness(request: SubRequest) -> TaskHarness:
    return request.getfixturevalue(request.param)


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceHarness:
    service: TaskService
    tickets: FakeTicketRepository
    task_ledger: TaskLedger
    contracts: FakeContractRepository
    clock: FakeClock
    ticket_id: int

    @property
    def tasks(self) -> FakeTaskRepository:
        return FakeTaskRepository(ledger=self.task_ledger)

    @property
    def attempts(self) -> FakeAttemptRepository:
        return FakeAttemptRepository(ledger=self.task_ledger)

    def held(self, task_key: TaskId) -> TaskRecord:
        record = self.tasks.task(self.ticket_id, task_key)
        assert record is not None
        return record


def create_start_request(
    *,
    task_key: TaskId = FIRST_TASK,
    worker: Worker = 'engineer',
    mode: ArchitectMode | None = None,
    owned: tuple[str, ...] = (OWNED_FILE,),
    acceptance_count: int = 1,
) -> StartRequest:
    return StartRequest(
        task_key=task_key,
        worker=worker,
        mode=mode,
        owned=owned,
        acceptance_count=acceptance_count,
        head=BASE_COMMIT,
    )


def create_git_facts(*, changed_files: frozenset[str] = frozenset({OWNED_FILE})) -> GitFacts:
    return GitFacts(
        head=DONE_COMMIT,
        base_resolves=True,
        base_is_ancestor=True,
        changed_files=changed_files,
        named_commit=DONE_COMMIT,
    )


def create_verify_request(seen: TaskRecord, *, changed_files: frozenset[str]) -> VerifyRequest:
    return VerifyRequest(
        seen=seen,
        commit=DONE_COMMIT,
        assertions={},
        git=create_git_facts(changed_files=changed_files),
        brief=Brief(text=BRIEF_TEXT),
    )


def verify_as_asked(harness: ServiceHarness, changed_files: frozenset[str]) -> TaskRecord:
    seen = harness.service.prepare_verification(SERVICE_SLUG, FIRST_TASK)
    request = create_verify_request(seen, changed_files=changed_files)
    return harness.service.verify(SERVICE_SLUG, request)


def create_receipt(key: str, *, head: str = DONE_COMMIT) -> Receipt:
    return Receipt(
        key=key,
        argv=('true',),
        outcome='pass',
        exit=0,
        duration_ms=1,
        stdout_tail=redact(''),
        stderr_tail=redact(''),
        digest='digest',
        head=head,
        phase='task',
        at=SERVICE_MOMENT,
    )


def create_command(key: str) -> ApprovedCommand:
    return ApprovedCommand(
        key=key, argv=('true',), expect_exit=0, timeout=10, approved_by='the user'
    )


@pytest.fixture
def service_harness() -> ServiceHarness:
    tickets = FakeTicketRepository()
    record = tickets.stage(SERVICE_SLUG, create_ticket_section(SERVICE_SLUG), ())
    task_ledger = TaskLedger()
    contracts = FakeContractRepository(ledger=ContractLedger())
    clock = create_fake_clock(SERVICE_MOMENT)
    service = TaskService(
        tickets=tickets,
        tasks=FakeTaskRepository(ledger=task_ledger),
        attempts=FakeAttemptRepository(ledger=task_ledger),
        contracts=contracts,
        clock=clock,
    )
    return ServiceHarness(
        service=service,
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
