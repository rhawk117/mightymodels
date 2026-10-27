"""Builders and shared values for the closing service tests."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from mightymodels_core.contract.records import Approval, ApprovedCommand
from mightymodels_core.investigations import InvestigationRecord, LedgerRecord
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.reviews.services import ReviewDecisionService
from mightymodels_core.ticket_closing import CloseRequest, ClosingService

from tests.core.contract.fakes import ContractLedger, FakeContractRepository
from tests.core.investigations.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from tests.core.primitives.clock import create_fake_clock
from tests.core.reviews.fakes import (
    FakeReviewDecisionRepository,
    FakeReviewRepository,
    ReviewLedger,
)
from tests.core.tasks.fakes import (
    FakeAttemptRepository,
    FakeTaskRepository,
    TaskLedger,
)
from tests.core.ticket_closing.closing_builders import (
    ARCHIVE_PATH,
    PLAN_TASK,
    REVIEW_RUN,
    SERVICE_BRANCH,
    SERVICE_MOMENT,
    SERVICE_SLUG,
    create_decided,
    create_facts,
    create_finding,
    create_lines,
    create_resolved,
    create_review_run,
    create_task,
    create_ticket_section,
)
from tests.core.ticket_closing.fakes import FakeClosingRepository
from tests.core.ticket_decisions.fakes import FakeTicketDecisionRepository
from tests.core.tickets.fakes import FakeTicketRepository

if TYPE_CHECKING:
    from mightymodels_core.ticket_closing import CloseFacts
    from mightymodels_core.tickets import TicketRecord

LINKED = Slug('linked-probe')
LENGTHENED_LINE = 'password=a ' * 360


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceHarness:
    service: ClosingService
    tickets: FakeTicketRepository
    closings: FakeClosingRepository
    ticket_decisions: FakeTicketDecisionRepository
    ticket_id: int

    def request_for(
        self, seen: TicketRecord, *, facts: CloseFacts | None = None, shipped: str = 'the service'
    ) -> CloseRequest:
        return CloseRequest(
            seen=seen,
            facts=facts or create_facts(),
            lines=create_lines(shipped),
            archive=ARCHIVE_PATH,
        )

    def request(
        self, *, facts: CloseFacts | None = None, shipped: str = 'the service'
    ) -> CloseRequest:
        return self.request_for(self.service.prepare(SERVICE_SLUG), facts=facts, shipped=shipped)

    def status(self) -> str:
        return self.tickets.staged_ticket(SERVICE_SLUG).status


def create_decision_entry(seq: int, text: str) -> LedgerRecord:
    return LedgerRecord(
        seq=seq,
        round=1,
        kind='decision',
        text=redact(text),
        source='code-scout',
        cite=None,
        supersedes=(),
        at=SERVICE_MOMENT,
        head='abc1234',
    )


def seed_review(ledger: ReviewLedger) -> None:
    ledger.runs[REVIEW_RUN] = create_review_run()
    ledger.findings[REVIEW_RUN] = {key: create_finding(key) for key in ('F1', 'F2')}
    ledger.dispositions[REVIEW_RUN] = {
        'F1': create_decided('F1', 'fix'),
        'F2': create_decided('F2', 'dismiss'),
    }
    ledger.outcomes[REVIEW_RUN] = {'F1': create_resolved('F1')}


def seed_investigation(ledger: InvestigationLedger) -> None:
    investigations = FakeInvestigationRepository(ledger=ledger)
    investigations.add_investigation(
        InvestigationRecord(key=LINKED, target=redact('a target'), kind='behavior')
    )
    investigations.append(LINKED, [create_decision_entry(1, 'use a policy')])


def create_service_command() -> ApprovedCommand:
    return ApprovedCommand(
        key='T1.AC-1', argv=('true',), expect_exit=0, timeout=10, approved_by='the user'
    )


def create_service_harness() -> ServiceHarness:
    tickets = FakeTicketRepository(recorded_investigations=(LINKED,))
    record = tickets.stage(
        SERVICE_SLUG, replace(create_ticket_section(), branch=SERVICE_BRANCH), (LINKED,)
    )
    task_ledger, review_ledger = TaskLedger(), ReviewLedger()
    investigation_ledger = InvestigationLedger()
    task_ledger.held[record.id, PLAN_TASK] = create_task()
    seed_review(review_ledger)
    seed_investigation(investigation_ledger)
    contracts = FakeContractRepository(ledger=ContractLedger())
    contracts.approve(
        record.id, [create_service_command()], Approval(at=SERVICE_MOMENT, head='base001')
    )
    closings = FakeClosingRepository()
    ticket_decisions = FakeTicketDecisionRepository(decided_at=SERVICE_MOMENT)
    clock = create_fake_clock(SERVICE_MOMENT)
    service = ClosingService(
        tickets=tickets,
        tasks=FakeTaskRepository(ledger=task_ledger),
        attempts=FakeAttemptRepository(ledger=task_ledger),
        contracts=contracts,
        review_decisions=ReviewDecisionService(
            reviews=FakeReviewRepository(ledger=review_ledger),
            decisions=FakeReviewDecisionRepository(ledger=review_ledger),
            clock=clock,
        ),
        investigations=FakeInvestigationRepository(ledger=investigation_ledger),
        closings=closings,
        ticket_decisions=ticket_decisions,
        clock=clock,
    )
    return ServiceHarness(
        service=service,
        tickets=tickets,
        closings=closings,
        ticket_decisions=ticket_decisions,
        ticket_id=record.id,
    )
