"""Builders and shared values for the snapshot tests."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.contract import ApprovedCommand, Receipt
from mightymodels_core.database import ConnectionOptions, open_database
from mightymodels_core.edge import create_database_spec
from mightymodels_core.investigations import AddRequest, IncomingEntry, StartRequest
from mightymodels_core.primitives import RepositoryKey, Slug, TaskId, redact
from mightymodels_core.reviews import IncomingDisposition, IncomingFinding
from mightymodels_core.reviews import StartRequest as ReviewStartRequest
from mightymodels_core.snapshot import RepositoryFacts
from mightymodels_core.tasks import MarkRequest
from mightymodels_core.tasks import StartRequest as TaskStartRequest
from mightymodels_core.ticket_decisions import SqliteTicketDecisionRepository
from mightymodels_core.tickets import SqliteTicketRepository, TicketSection, Tracker
from mightymodels_core.units_of_work import (
    InvestigationWork,
    ReviewWork,
    SnapshotRead,
    TaskWork,
    write_entry,
)

from tests.core.primitives.clock import create_fake_clock

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RunId
    from mightymodels_core.schemas.contract import Outcome
    from mightymodels_core.ticket_decisions import IncomingDecision

HEAD = 'a' * 40
MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
OLD_HEAD = 'b' * 40
REPOSITORY_FACTS = RepositoryFacts(
    branch='feat/widget', head=HEAD, dirty=('src/a.py', 'src/b.py', 'src/c.py'), refusal=None
)
FIRST_SUMMARY = 'add the widget'
OTHER_SUMMARY = 'a ticket of the other repository'


def create_receipt(key: str, *, outcome: Outcome, head: str) -> Receipt:
    return Receipt(
        key=key,
        argv=('pytest', '-q', key),
        outcome=outcome,
        exit=0,
        duration_ms=5,
        stdout_tail=redact(''),
        stderr_tail=redact(''),
        digest='digest',
        head=head,
        phase='task',
        at=MOMENT,
    )


def create_defect(source: str) -> IncomingFinding:
    return IncomingFinding(
        sources=(source,),
        severity='High',
        kind='defect',
        security=False,
        title=f'defect found by {source}',
        location=f'src/{source}.py:10',
        fix='fix it',
        verify='pytest -q',
        evidence=None,
    )


def create_section(summary: str) -> TicketSection:
    return TicketSection(
        ticket='.mightymodels/add-widget/ticket.yml',
        summary=redact(summary),
        branch='feat/widget',
        scope='med',
        plan_first=False,
        auto_escalate=False,
        models={'engineer': 'sonnet'},
        tracker=Tracker(issue=7, jira=None),
        context=(),
        validated_at=MOMENT,
    )


def create_command(key: str) -> ApprovedCommand:
    return ApprovedCommand(
        key=key, argv=('pytest', '-q', key), expect_exit=0, timeout=60, approved_by='owner'
    )


def seed_investigation(database: Database, repository_key: RepositoryKey, clock: Clock) -> Slug:
    work = InvestigationWork(database=database, repository_key=repository_key, clock=clock)
    with work.write() as unit:
        started = unit.investigations.start(StartRequest(target='cache the widget', kind='change'))
        entries = [
            IncomingEntry(kind='decision', text='use sqlite', source='user'),
            IncomingEntry(kind='open', text='which cache size', source='primary'),
        ]
        unit.investigations.add(
            started.investigation, AddRequest(round=1, entries=entries, head=HEAD)
        )
    return started.investigation


def seed_ticket(
    database: Database,
    repository_key: RepositoryKey,
    clock: Clock,
    slug: Slug,
    investigation: Slug,
) -> Slug:
    work = TaskWork(database=database, repository_key=repository_key, clock=clock)
    with work.write() as unit:
        unit.tasks.tickets.stage(slug, create_section(FIRST_SUMMARY), (investigation,))
        unit.contracts.approve(
            slug, [create_command(key) for key in ('T1.AC-1', 'T1.AC-2', 'T2.AC-1')], head=HEAD
        )
        unit.contracts.record(
            slug,
            [
                create_receipt('T1.AC-1', outcome='pass', head=HEAD),
                create_receipt('T1.AC-2', outcome='fail', head=OLD_HEAD),
            ],
        )
        start = TaskStartRequest(
            task_key=TaskId('T1'),
            worker='engineer',
            mode=None,
            owned=('src/a.py',),
            acceptance_count=2,
            head=HEAD,
        )
        unit.tasks.start(slug, start)
        unit.tasks.mark(slug, MarkRequest(task_key=TaskId('T1'), to='blocked', reason='a wall'))
    return slug


def seed_ticket_decision(
    database: Database,
    repository_key: RepositoryKey,
    clock: Clock,
    slug: Slug,
    decision: IncomingDecision,
) -> None:
    with write_entry(database, repository_key) as entry:
        tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
        decisions = SqliteTicketDecisionRepository(unit=entry.unit, clock=clock)
        decisions.add(tickets.staged_ticket(slug).id, decision)


def seed_review(
    database: Database, repository_key: RepositoryKey, clock: Clock, seeded: Slug
) -> RunId:
    work = ReviewWork(database=database, repository_key=repository_key, clock=clock)
    request = ReviewStartRequest(
        scope='branch', base='main', slug=seeded, depth='standard', emphasis='balanced'
    )
    with work.write() as unit:
        run = unit.reviews.start(request, HEAD)
        findings = [create_defect(source) for source in ('MV-1', 'MV-2')]
        added = unit.reviews.add_findings(run.run_id, findings)
        decided = {added.changed[0].key: IncomingDisposition(decision='defer', reason='later')}
        unit.decisions.dispose(run.run_id, decided, 'owner')
    return run.run_id


def seed_crowded_ledger(
    database: Database, repository_key: RepositoryKey, clock: Clock, investigation: Slug
) -> Slug:
    work = InvestigationWork(database=database, repository_key=repository_key, clock=clock)
    entries = [
        IncomingEntry(kind='decision', text='use wal mode', source='user'),
        IncomingEntry(kind='open', text='which retention', source='primary'),
    ]
    with work.write() as unit:
        unit.investigations.add(investigation, AddRequest(round=2, entries=entries, head=HEAD))
    return investigation


def seed_crowded_tasks(
    database: Database, repository_key: RepositoryKey, clock: Clock, seeded: Slug
) -> Slug:
    work = TaskWork(database=database, repository_key=repository_key, clock=clock)
    start = TaskStartRequest(
        task_key=TaskId('T2'),
        worker='engineer',
        mode=None,
        owned=('src/b.py',),
        acceptance_count=1,
        head=HEAD,
    )
    receipts = [
        create_receipt('T1.AC-2', outcome='pass', head=HEAD),
        create_receipt('T2.AC-1', outcome='pass', head=HEAD),
    ]
    with work.write() as unit:
        unit.contracts.record(seeded, receipts)
        unit.tasks.start(seeded, start)
        unit.tasks.mark(seeded, MarkRequest(task_key=TaskId('T2'), to='blocked', reason='a wall'))
    return seeded


def seed_crowded_review(
    database: Database, repository_key: RepositoryKey, clock: Clock, reviewed: RunId
) -> RunId:
    work = ReviewWork(database=database, repository_key=repository_key, clock=clock)
    with work.write() as unit:
        added = unit.reviews.add_findings(reviewed, [create_defect('MV-3')])
        decided = {added.changed[0].key: IncomingDisposition(decision='defer', reason='later')}
        unit.decisions.dispose(reviewed, decided, 'owner')
    return reviewed


@dataclass(slots=True, kw_only=True, frozen=True)
class CrowdedSnapshot:
    read: SnapshotRead
    slug: Slug


@contextmanager
def open_crowded_snapshot(directory: Path) -> Generator[CrowdedSnapshot]:
    key = RepositoryKey('owner/repo')
    clock = create_fake_clock(MOMENT)
    opened = open_database(
        directory.joinpath('mightymodels.db'), create_database_spec(), ConnectionOptions()
    )
    try:
        investigation = seed_investigation(opened, key, clock)
        seeded = seed_ticket(opened, key, clock, Slug('add-widget'), investigation)
        reviewed = seed_review(opened, key, clock, seeded)
        seed_crowded_ledger(opened, key, clock, investigation)
        seed_crowded_tasks(opened, key, clock, seeded)
        seed_crowded_review(opened, key, clock, reviewed)
        yield CrowdedSnapshot(
            read=SnapshotRead(database=opened, repository_key=key, clock=clock), slug=seeded
        )
    finally:
        opened.close()
