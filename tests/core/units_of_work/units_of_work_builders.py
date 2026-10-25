"""Builders and constants the unit-of-work tests share, imported by the suite and the conftests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.contract import SqliteContractRepository
from mightymodels_core.contract.records import Approval, ApprovedCommand
from mightymodels_core.crashouts import SqliteCrashoutRepository
from mightymodels_core.investigations import InvestigationRecord, SqliteInvestigationRepository
from mightymodels_core.primitives import RunId, Slug, TaskId, redact
from mightymodels_core.reviews import (
    DecidedFinding,
    FindingRecord,
    ReviewRunRecord,
    SqliteReviewDecisionRepository,
    SqliteReviewRepository,
)
from mightymodels_core.schemas.repositories import REPOSITORY_BY_KEY, RepositoryKeyParams
from mightymodels_core.similarity import SqliteScoutReportRepository, SqliteSimilarityRepository
from mightymodels_core.tasks import (
    Attempt,
    FailedFix,
    SqliteAttemptRepository,
    SqliteTaskRepository,
    Transition,
)
from mightymodels_core.ticket_closing import ClosingRecord
from mightymodels_core.tickets import SqliteTicketRepository

if TYPE_CHECKING:
    from mightymodels_core.database import Database, Unit
    from mightymodels_core.primitives import RepositoryKey
    from mightymodels_core.units_of_work import TicketWork
    from mightymodels_core.units_of_work.tickets import TicketWriteUnit
    from mightymodels_core.workspace import Workspace


@dataclass(slots=True, kw_only=True, frozen=True)
class UnitsOfWorkHarness:
    database: Database
    workspace: Workspace


def count_repositories(database: Database, repository_key: RepositoryKey) -> int:
    with database.read() as unit:
        row = unit.one(REPOSITORY_BY_KEY, RepositoryKeyParams(repository_key=repository_key))
    return 0 if row is None else 1


SQLITE_STORES = (
    SqliteAttemptRepository,
    SqliteContractRepository,
    SqliteCrashoutRepository,
    SqliteInvestigationRepository,
    SqliteReviewDecisionRepository,
    SqliteReviewRepository,
    SqliteScoutReportRepository,
    SqliteSimilarityRepository,
    SqliteTaskRepository,
    SqliteTicketRepository,
)


def unit_of(store: object) -> Unit:
    assert isinstance(store, SQLITE_STORES)
    return store.unit


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
