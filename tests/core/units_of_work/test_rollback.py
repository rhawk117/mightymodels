from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract.records import Approval, ApprovedCommand
from mightymodels_core.investigations import InvestigationRecord
from mightymodels_core.primitives import RunId, Slug, TaskId, redact
from mightymodels_core.reviews import DecidedFinding, FindingRecord, ReviewRunRecord
from mightymodels_core.tasks import Attempt, FailedFix, Transition
from mightymodels_core.ticket_closing import ClosingRecord

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from mightymodels_core.units_of_work import TicketWork
    from mightymodels_core.units_of_work.tickets import TicketWriteUnit

pytestmark = [pytest.mark.integration]


MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
TASK = TaskId('T1')
REVIEW_RUN = RunId('20260506-070809')
FINDING_KEY = 'MV-1'
COMMAND_KEY = 'T1.AC-1'


class UnitFailedError(Exception):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(ticket_id)
        self.ticket_id = ticket_id


def write_task_stores(unit: TicketWriteUnit, ticket_id: int) -> None:
    started = Transition(
        task_key=TASK, before='pending', after='in-progress', reasons=(), head='abc1234', at=MOMENT
    )
    unit.closing.tasks.record_start(
        ticket_id, started, Attempt(worker='engineer', mode=None, owned=('src/a.py',))
    )
    fix = FailedFix(task_key=TASK, hypothesis=redact('a hypothesis'), at=MOMENT)
    unit.closing.attempts.record_failed_fix(ticket_id, fix)
    command = ApprovedCommand(
        key=COMMAND_KEY, argv=('make', 'test'), expect_exit=0, timeout=300, approved_by='planner'
    )
    unit.closing.contracts.approve(ticket_id, [command], Approval(at=MOMENT, head='abc1234'))


def write_review_stores(unit: TicketWriteUnit, slug: Slug) -> None:
    run = ReviewRunRecord(
        run_id=REVIEW_RUN,
        slug=slug,
        scope='branch',
        base='main',
        head='abc1234',
        depth='standard',
        emphasis='balanced',
        weights={'merge-vader': 1.0},
        personas=('merge-vader',),
        models={'merge-vader': None},
        created_at=MOMENT,
    )
    finding = FindingRecord(
        key=FINDING_KEY,
        sources=('merge-vader',),
        severity='High',
        kind='defect',
        security=False,
        title=redact('a defect'),
        location=redact('src/a.py:10'),
        fix=redact('fix it'),
        verify=redact('pytest -q'),
        evidence=None,
        conflict=None,
    )
    decided = DecidedFinding(
        finding_key=FINDING_KEY,
        decision='fix',
        reason=redact('worth doing'),
        by=redact('owner'),
        at=MOMENT,
    )
    unit.closing.review_decisions.reviews.record_run(run)
    unit.closing.review_decisions.reviews.record_findings(REVIEW_RUN, [finding])
    unit.closing.review_decisions.decisions.record_dispositions(REVIEW_RUN, [decided])


def fail_after_writes(ticket_work: TicketWork, slug: Slug) -> None:
    investigation = InvestigationRecord(
        key=Slug('first-look'), target=redact('target'), kind='behavior'
    )
    closing = ClosingRecord(
        closed_at=MOMENT,
        head='abc1234',
        shipped=redact('shipped'),
        pr='https://example.test/pull/7',
        gotchas=(),
        archive='archive/add-widget.tar',
    )
    with ticket_work.write() as unit:
        unit.tickets.investigations.add_investigation(investigation)
        ticket = unit.tickets.stage(slug, unit.files.source(slug))
        write_task_stores(unit, ticket.id)
        write_review_stores(unit, slug)
        unit.closing.closings.record_closing(ticket.id, closing)
        raise UnitFailedError(ticket.id)


@pytest.fixture
def failed_ticket_id(request: FixtureRequest, ticket_work: TicketWork, slug: Slug) -> int:
    request.getfixturevalue('written_text')
    with pytest.raises(UnitFailedError) as failure:
        fail_after_writes(ticket_work, slug)

    return failure.value.ticket_id


class TestWriteUnitRollback:
    def test_error_in_a_write_unit_rolls_back_every_repositorys_writes(
        self, ticket_work: TicketWork, slug: Slug, failed_ticket_id: int
    ) -> None:
        with ticket_work.write() as unit:
            assert unit.tickets.tickets.ticket(slug) is None
            assert unit.tickets.investigations.investigation(Slug('first-look')) is None
            assert unit.closing.tasks.task(failed_ticket_id, TASK) is None
            assert unit.closing.attempts.failed_fixes(failed_ticket_id, TASK) == []
            assert unit.closing.contracts.commands(failed_ticket_id) == []
            assert unit.closing.review_decisions.reviews.run(REVIEW_RUN) is None
            assert unit.closing.review_decisions.decisions.dispositions(REVIEW_RUN) == []
            assert unit.closing.closings.closing(failed_ticket_id) is None

    @pytest.mark.usefixtures('failed_ticket_id')
    def test_error_in_a_write_unit_leaves_the_stored_file_in_place(
        self, ticket_work: TicketWork, slug: Slug, written_text: str
    ) -> None:
        with ticket_work.read() as unit:
            assert unit.files.source(slug).text == written_text
