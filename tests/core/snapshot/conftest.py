"""A real sqlite database with a ticket seeded in two repositories, and a SnapshotRead over each."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import ApprovedCommand
from mightymodels_core.database import ConnectionOptions, open_database
from mightymodels_core.edge import create_database_spec
from mightymodels_core.git import GitNoAnswerError
from mightymodels_core.investigations import AddRequest, IncomingEntry, StartRequest
from mightymodels_core.primitives import RepositoryKey, Slug, TaskId, redact
from mightymodels_core.reviews import IncomingDisposition
from mightymodels_core.reviews import StartRequest as ReviewStartRequest
from mightymodels_core.snapshot import RepositoryFacts
from mightymodels_core.tasks import MarkRequest
from mightymodels_core.tasks import StartRequest as TaskStartRequest
from mightymodels_core.tickets import TicketSection, Tracker
from mightymodels_core.units_of_work import InvestigationWork, ReviewWork, SnapshotRead, TaskWork

from tests.core.primitives.clock import create_fake_clock

from .snapshot_builders import HEAD, MOMENT, create_defect, create_receipt

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RunId

OLD_HEAD = 'b' * 40
FIRST_SUMMARY = 'add the widget'
OTHER_SUMMARY = 'a ticket of the other repository'


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


@pytest.fixture
def repository_key() -> RepositoryKey:
    return RepositoryKey('owner/repo')


@pytest.fixture
def other_repository_key() -> RepositoryKey:
    return RepositoryKey('other/repo')


@pytest.fixture
def database(tmp_path: Path) -> Generator[Database]:
    opened = open_database(
        tmp_path.joinpath('mightymodels.db'), create_database_spec(), ConnectionOptions()
    )
    yield opened
    opened.close()


@pytest.fixture
def slug() -> Slug:
    return Slug('add-widget')


@pytest.fixture
def clock() -> Clock:
    return create_fake_clock(MOMENT)


@pytest.fixture
def investigation_work(
    database: Database, repository_key: RepositoryKey, clock: Clock
) -> InvestigationWork:
    return InvestigationWork(database=database, repository_key=repository_key, clock=clock)


@pytest.fixture
def task_work(database: Database, repository_key: RepositoryKey, clock: Clock) -> TaskWork:
    return TaskWork(database=database, repository_key=repository_key, clock=clock)


@pytest.fixture
def review_work(database: Database, repository_key: RepositoryKey, clock: Clock) -> ReviewWork:
    return ReviewWork(database=database, repository_key=repository_key, clock=clock)


@pytest.fixture
def repository_facts() -> RepositoryFacts:
    return RepositoryFacts(
        branch='feat/widget', head=HEAD, dirty=('src/a.py', 'src/b.py', 'src/c.py'), refusal=None
    )


@pytest.fixture
def investigation(database: Database, repository_key: RepositoryKey, clock: Clock) -> Slug:
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


@pytest.fixture
def seeded(
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


@pytest.fixture
def reviewed(
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


@pytest.fixture
def other_seeded(
    database: Database, other_repository_key: RepositoryKey, clock: Clock, slug: Slug
) -> Slug:
    work = TaskWork(database=database, repository_key=other_repository_key, clock=clock)
    with work.write() as unit:
        unit.tasks.tickets.stage(slug, create_section(OTHER_SUMMARY), ())
    return slug


@pytest.fixture
def snapshot_read(database: Database, repository_key: RepositoryKey, clock: Clock) -> SnapshotRead:
    return SnapshotRead(database=database, repository_key=repository_key, clock=clock)


@pytest.fixture
def other_snapshot_read(
    database: Database, other_repository_key: RepositoryKey, clock: Clock
) -> SnapshotRead:
    return SnapshotRead(database=database, repository_key=other_repository_key, clock=clock)


@pytest.fixture
def refused_facts() -> RepositoryFacts:
    return RepositoryFacts(
        branch=None, head=None, dirty=None, refusal=GitNoAnswerError(detail='no repository')
    )
