from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.crashouts import CrashoutEntry
from mightymodels_core.database import ConnectionOptions, open_database
from mightymodels_core.edge import create_database_spec
from mightymodels_core.investigations import StartRequest as InvestigationStartRequest
from mightymodels_core.primitives import RepositoryKey, Slug, redact
from mightymodels_core.primitives.tests.clock import create_fake_clock
from mightymodels_core.reviews import StartRequest as ReviewStartRequest
from mightymodels_core.tickets import TicketAnswers, TicketSection, Tracker
from mightymodels_core.units_of_work import (
    InvestigationWork,
    JournalWork,
    ReviewWork,
    SnapshotRead,
    TaskWork,
    TicketWork,
)
from mightymodels_core.workspace import workspace_at

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RunId
    from mightymodels_core.workspace import Workspace


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
def workspace(tmp_path: Path) -> Workspace:
    return workspace_at(tmp_path.joinpath('project'))


@pytest.fixture
def clock() -> Clock:
    return create_fake_clock(datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC))


@pytest.fixture
def ticket_work(
    database: Database, repository_key: RepositoryKey, workspace: Workspace, clock: Clock
) -> TicketWork:
    return TicketWork(
        database=database, repository_key=repository_key, workspace=workspace, clock=clock
    )


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
def journal_work(database: Database, repository_key: RepositoryKey, clock: Clock) -> JournalWork:
    return JournalWork(database=database, repository_key=repository_key, clock=clock)


@pytest.fixture
def answers() -> TicketAnswers:
    return TicketAnswers(
        summary='add the widget',
        context=('one line', 'two lines'),
        scope='large',
        plan_first=True,
        branch='feat/widget',
    )


@pytest.fixture
def written_text(ticket_work: TicketWork, slug: Slug, answers: TicketAnswers) -> str:
    with ticket_work.write() as unit:
        text = unit.tickets.write(slug, answers, unit.files.slot(slug))
        unit.store(slug, text)
    return text


@pytest.fixture
def other_repository(
    database: Database, other_repository_key: RepositoryKey, clock: Clock
) -> RepositoryKey:
    registering = TaskWork(database=database, repository_key=other_repository_key, clock=clock)
    with registering.write():
        pass
    return other_repository_key


@pytest.fixture
def other_ticket_work(
    database: Database, other_repository: RepositoryKey, workspace: Workspace, clock: Clock
) -> TicketWork:
    return TicketWork(
        database=database, repository_key=other_repository, workspace=workspace, clock=clock
    )


@pytest.fixture
def other_investigation_work(
    database: Database, other_repository: RepositoryKey, clock: Clock
) -> InvestigationWork:
    return InvestigationWork(database=database, repository_key=other_repository, clock=clock)


@pytest.fixture
def other_task_work(database: Database, other_repository: RepositoryKey, clock: Clock) -> TaskWork:
    return TaskWork(database=database, repository_key=other_repository, clock=clock)


@pytest.fixture
def other_review_work(
    database: Database, other_repository: RepositoryKey, clock: Clock
) -> ReviewWork:
    return ReviewWork(database=database, repository_key=other_repository, clock=clock)


@pytest.fixture
def other_journal_work(
    database: Database, other_repository: RepositoryKey, clock: Clock
) -> JournalWork:
    return JournalWork(database=database, repository_key=other_repository, clock=clock)


@pytest.fixture
def other_snapshot_read(
    database: Database, other_repository: RepositoryKey, clock: Clock
) -> SnapshotRead:
    return SnapshotRead(database=database, repository_key=other_repository, clock=clock)


@pytest.fixture
def started_investigation(investigation_work: InvestigationWork) -> Slug:
    with investigation_work.write() as unit:
        return unit.investigations.start(
            InvestigationStartRequest(target='cache the widget', kind='change')
        ).investigation


@pytest.fixture
def started_review(review_work: ReviewWork) -> RunId:
    request = ReviewStartRequest(
        scope='branch', base='main', slug=None, depth='standard', emphasis='balanced'
    )
    with review_work.write() as unit:
        return unit.reviews.start(request, 'a' * 40).run_id


@pytest.fixture
def staged_slug(task_work: TaskWork, slug: Slug, clock: Clock) -> Slug:
    section = TicketSection(
        ticket='.mightymodels/add-widget/ticket.yml',
        summary=redact('add the widget'),
        branch='feat/widget',
        scope='med',
        plan_first=False,
        auto_escalate=False,
        models={'engineer': 'sonnet'},
        tracker=Tracker(issue=None, jira=None),
        context=(),
        validated_at=clock.now(),
    )
    with task_work.write() as unit:
        unit.tasks.tickets.stage(slug, section, ())
    return slug


@pytest.fixture
def journaled(journal_work: JournalWork) -> None:
    entry = CrashoutEntry(
        ticket_key=None,
        branch=None,
        severity='heated',
        verdict='split',
        rant='the widget broke',
        failures=('a failure',),
        root_cause='a cause',
        corrective_action='an action',
        barked_back=False,
    )
    with journal_work.write() as unit:
        unit.crashouts.add(entry)


@pytest.fixture
def staged_ticket(ticket_work: TicketWork, slug: Slug, written_text: str) -> Slug:
    assert written_text
    with ticket_work.write() as unit:
        unit.tickets.stage(slug, unit.files.source(slug))
    return slug
