from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract.records import Approval, ApprovedCommand
from mightymodels_core.contract.tests.fakes import ContractLedger, FakeContractRepository
from mightymodels_core.investigations import InvestigationRecord, LedgerRecord
from mightymodels_core.primitives import RedactedTextTooLongError, Slug, redact
from mightymodels_core.primitives.tests.clock import create_fake_clock
from mightymodels_core.reviews.services import ReviewDecisionService
from mightymodels_core.tasks.tests.fakes import (
    FakeAttemptRepository,
    FakeTaskRepository,
    TaskLedger,
)
from mightymodels_core.ticket_closing import (
    LIVE_DEBUG,
    CloseRequest,
    ClosingService,
    LiveWorkRemainsError,
    ShippedRequiredError,
    TicketMovedError,
    TooManyGotchasError,
)
from mightymodels_core.tickets import ClosedTicketError, NotStagedError
from mightymodels_core.tickets.tests.fakes import FakeTicketRepository

from tests.core.investigations.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from tests.core.reviews.fakes import (
    FakeReviewDecisionRepository,
    FakeReviewRepository,
    ReviewLedger,
)
from tests.core.ticket_closing.conftest import (
    ARCHIVE_PATH,
    PLAN_TASK,
    REVIEW_RUN,
    SERVICE_BRANCH,
    SERVICE_MOMENT,
    SERVICE_SLUG,
    create_branch_facts,
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


@pytest.fixture
def service_harness() -> ServiceHarness:
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
    command = ApprovedCommand(
        key='T1.AC-1', argv=('true',), expect_exit=0, timeout=10, approved_by='the user'
    )
    contracts.approve(record.id, [command], Approval(at=SERVICE_MOMENT, head='base001'))
    closings = FakeClosingRepository()
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
        clock=clock,
    )
    return ServiceHarness(service=service, tickets=tickets, closings=closings, ticket_id=record.id)


@pytest.fixture
def closed_harness(service_harness: ServiceHarness) -> ServiceHarness:
    service_harness.service.close(SERVICE_SLUG, service_harness.request())
    return service_harness


@pytest.fixture
def stale_request(service_harness: ServiceHarness) -> CloseRequest:
    seen = service_harness.service.prepare(SERVICE_SLUG)
    service_harness.tickets.stage(SERVICE_SLUG, replace(seen.section, branch='feat/moved'), ())
    return service_harness.request_for(seen)


class TestCheck:
    def test_a_ticket_with_no_live_work_is_not_blocked(
        self, service_harness: ServiceHarness
    ) -> None:
        checked = service_harness.service.check(SERVICE_SLUG, create_facts())

        assert (checked.blocked, checked.blockers, checked.git_refusal) == (False, (), None)

    def test_live_work_is_answered_as_a_value_and_nothing_is_written(
        self, service_harness: ServiceHarness
    ) -> None:
        checked = service_harness.service.check(SERVICE_SLUG, create_facts(debug_note=True))

        assert (checked.blocked, checked.blockers) == (True, (LIVE_DEBUG,))
        assert service_harness.status() == 'staged'

    def test_git_not_consulted_is_reported_and_the_branch_is_not_judged(
        self, service_harness: ServiceHarness
    ) -> None:
        facts = replace(
            create_facts(branch=create_branch_facts(unpushed=5)), git_refusal='no git binary'
        )

        checked = service_harness.service.check(SERVICE_SLUG, facts)

        assert (checked.blocked, checked.git_refusal) == (False, 'no git binary')

    def test_a_closed_ticket_is_answered(self, closed_harness: ServiceHarness) -> None:
        checked = closed_harness.service.check(SERVICE_SLUG, create_facts())

        assert checked.blocked is False

    def test_a_ticket_never_staged_is_refused(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(NotStagedError):
            service_harness.service.check(Slug('unstaged-subject'), create_facts())


class TestClose:
    def test_the_ticket_is_marked_closed_and_its_closing_stored(
        self, service_harness: ServiceHarness
    ) -> None:
        closed = service_harness.service.close(SERVICE_SLUG, service_harness.request())

        assert service_harness.status() == 'closed'
        assert service_harness.closings.closing(service_harness.ticket_id) == closed.closing
        assert closed.closing.closed_at == SERVICE_MOMENT
        assert (closed.closing.head, closed.closing.archive) == ('abc1234', ARCHIVE_PATH)
        assert closed.closing.shipped == 'the service'

    def test_the_archive_record_carries_the_work_the_service_read(
        self, service_harness: ServiceHarness
    ) -> None:
        archive = service_harness.service.close(SERVICE_SLUG, service_harness.request()).archive

        assert archive.slug == SERVICE_SLUG
        assert archive.investigations == (LINKED,)
        assert {key: task.status for key, task in archive.tasks.items()} == {PLAN_TASK: 'verified'}
        assert [(item.key, item.outcome) for item in archive.verification] == [
            ('T1.AC-1', 'never-run')
        ]
        assert [(item.text, item.origin) for item in archive.decisions] == [
            ('use a policy', 'linked-probe e1')
        ]
        assert archive.review is not None
        assert archive.review.by_decision == {'fixed': ('F1',), 'dismiss': ('F2',)}

    def test_git_not_consulted_closes_the_ticket_with_no_head(
        self, service_harness: ServiceHarness
    ) -> None:
        facts = replace(create_facts(), git_refusal='no git binary', head=None, branch=None)

        closed = service_harness.service.close(SERVICE_SLUG, service_harness.request(facts=facts))

        assert closed.closing.head is None
        assert service_harness.status() == 'closed'

    def test_live_work_refuses_the_close_and_writes_nothing(
        self, service_harness: ServiceHarness
    ) -> None:
        request = service_harness.request(facts=create_facts(debug_note=True))

        with pytest.raises(LiveWorkRemainsError) as refused:
            service_harness.service.close(SERVICE_SLUG, request)

        assert refused.value.blockers == (LIVE_DEBUG,)
        assert service_harness.status() == 'staged'
        assert service_harness.closings.closing(service_harness.ticket_id) is None

    def test_a_ticket_that_moved_while_git_was_asked_is_refused_and_nothing_is_written(
        self, service_harness: ServiceHarness, stale_request: CloseRequest
    ) -> None:
        with pytest.raises(TicketMovedError) as refused:
            service_harness.service.close(SERVICE_SLUG, stale_request)

        assert refused.value.changed == ('branch',)
        assert service_harness.status() == 'staged'
        assert service_harness.closings.closing(service_harness.ticket_id) is None

    def test_a_blank_shipped_line_is_refused_and_nothing_is_written(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(ShippedRequiredError):
            service_harness.service.close(SERVICE_SLUG, service_harness.request(shipped=' \n '))

        assert service_harness.status() == 'staged'

    def test_a_fourth_gotcha_is_refused_and_nothing_is_written(
        self, service_harness: ServiceHarness
    ) -> None:
        request = service_harness.request()
        lines = replace(request.lines, gotchas=('a', 'b', 'c', 'd'))

        with pytest.raises(TooManyGotchasError):
            service_harness.service.close(SERVICE_SLUG, replace(request, lines=lines))

        assert service_harness.closings.closing(service_harness.ticket_id) is None

    def test_a_line_that_redaction_lengthens_past_its_limit_is_refused(
        self, service_harness: ServiceHarness
    ) -> None:
        request = service_harness.request(shipped=LENGTHENED_LINE)

        with pytest.raises(RedactedTextTooLongError):
            service_harness.service.close(SERVICE_SLUG, request)

        assert service_harness.status() == 'staged'

    def test_a_closed_ticket_cannot_be_closed_again(self, closed_harness: ServiceHarness) -> None:
        with pytest.raises(ClosedTicketError):
            closed_harness.service.close(SERVICE_SLUG, closed_harness.request())
