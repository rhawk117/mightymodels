"""Builders, constants and harnesses shared by the contract tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

from mightymodels_core.contract import (
    Approval,
    ApprovedCommand,
    ContractService,
    Receipt,
)
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.tickets import TicketSection, Tracker

from tests.core.contract.fakes import ContractLedger, FakeContractRepository
from tests.core.primitives.clock import create_fake_clock
from tests.core.tickets.fakes import FakeTicketRepository

if TYPE_CHECKING:
    from mightymodels_core.contract import ContractRepository
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
