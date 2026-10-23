"""The closing repository over a real sqlite unit and over the fake, one fixture for both."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, DatabaseSpec, open_database
from mightymodels_core.primitives import RunId, Slug, TaskId, redact
from mightymodels_core.reviews import (
    DecidedFinding,
    FindingRecord,
    LatestReview,
    ResolvedFinding,
    ReviewRunRecord,
)
from mightymodels_core.schemas import DECLARATIONS
from mightymodels_core.schemas.repositories import ENSURE_REPOSITORY, RepositoryKeyParams
from mightymodels_core.schemas.tickets import TICKET_BY_SLUG, TicketSlugParams
from mightymodels_core.tasks import TaskRecord
from mightymodels_core.ticket_closing import (
    BranchFacts,
    CloseFacts,
    ClosingLines,
    ClosingRecord,
    SqliteClosingRepository,
)
from mightymodels_core.tickets import SqliteTicketRepository, TicketSection, Tracker

from tests.core.ticket_closing.fakes import FakeClosingRepository

if TYPE_CHECKING:
    from collections.abc import Collection, Generator
    from pathlib import Path

    from _pytest.fixtures import SubRequest
    from _pytest.mark import ParameterSet
    from mightymodels_core.database import Database
    from mightymodels_core.schemas.reviews import Decision
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.ticket_closing import ClosingRepository

SQL = files('mightymodels_core.sql')
TICKET_SLUG = Slug('closing-subject')
FAKE_TICKET_ID = 1
SERVICE_SLUG = Slug('closing-service')
SERVICE_BRANCH = 'feat/stable-core'
SERVICE_MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
ARCHIVE_PATH = '.mightymodels/archive/closing-service.md'
PLAN_TASK = TaskId('T1')
REVIEW_RUN = RunId('20260506-070809')


@dataclass(slots=True, kw_only=True, frozen=True)
class ClosingHarness:
    repository: ClosingRepository
    ticket_id: int


def create_closing(shipped: str, *, closed_day: int = 2) -> ClosingRecord:
    return ClosingRecord(
        closed_at=datetime(2026, 1, closed_day, 3, 4, 5, tzinfo=UTC),
        head='abc1234',
        shipped=redact(shipped),
        pr='https://example.test/pull/7',
        gotchas=(redact('first gotcha'), redact('second gotcha')),
        archive='archive/closing-subject.tar',
    )


def create_ticket_section() -> TicketSection:
    return TicketSection(
        ticket='.mightymodels/a-ticket/ticket.yml',
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


def closing_implementation_cases() -> list[ParameterSet]:
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
def staged_ticket_id(database: Database) -> int:
    with database.write() as unit:
        repository = unit.one(ENSURE_REPOSITORY, RepositoryKeyParams(repository_key='owner/repo'))
        assert repository is not None
        tickets = SqliteTicketRepository(unit=unit, repository_id=repository.id)
        tickets.stage(TICKET_SLUG, create_ticket_section(), ())
        row = unit.one(
            TICKET_BY_SLUG, TicketSlugParams(repository_id=repository.id, slug=TICKET_SLUG)
        )
        assert row is not None
    return row.id


@pytest.fixture
def sqlite_harness(database: Database, staged_ticket_id: int) -> Generator[ClosingHarness]:
    with database.write() as unit:
        yield ClosingHarness(
            repository=SqliteClosingRepository(unit=unit), ticket_id=staged_ticket_id
        )


@pytest.fixture
def fake_harness() -> ClosingHarness:
    return ClosingHarness(repository=FakeClosingRepository(), ticket_id=FAKE_TICKET_ID)


@pytest.fixture(params=closing_implementation_cases())
def harness(request: SubRequest) -> ClosingHarness:
    return request.getfixturevalue(request.param)


def create_branch_facts(
    *,
    exists: bool = True,
    unpushed: int | None = 0,
    checked_out: bool = False,
    dirty: int | None = 0,
) -> BranchFacts:
    return BranchFacts(exists=exists, unpushed=unpushed, checked_out=checked_out, dirty=dirty)


def create_facts(
    *, debug_note: bool = False, git_refusal: str | None = None, branch: BranchFacts | None = None
) -> CloseFacts:
    return CloseFacts(
        debug_note=debug_note,
        git_refusal=git_refusal,
        head='abc1234',
        branch=branch or create_branch_facts(),
    )


def create_lines(
    shipped: str = 'the closing service', gotchas: tuple[str, ...] = ('first gotcha',)
) -> ClosingLines:
    return ClosingLines(shipped=shipped, pr='https://example.test/pull/9', gotchas=gotchas)


def create_task(key: str = 'T1', status: TaskStatus = 'verified') -> TaskRecord:
    return TaskRecord(key=TaskId(key), status=status)


def create_finding(key: str) -> FindingRecord:
    return FindingRecord(
        key=key,
        sources=('merge-vader',),
        severity='High',
        kind='defect',
        security=False,
        title=redact('a defect'),
        location=redact('src/a.py:10'),
        fix=redact('fix it'),
        verify=redact('pytest -q'),
        evidence=None,
        conflict=redact('the other reviewer disagrees'),
    )


def create_decided(key: str, decision: Decision) -> DecidedFinding:
    return DecidedFinding(
        finding_key=key,
        decision=decision,
        reason=redact('worth\n  doing'),
        by=redact('owner'),
        at=SERVICE_MOMENT,
    )


def create_resolved(key: str) -> ResolvedFinding:
    return ResolvedFinding(
        finding_key=key, result='fixed', commit='def5678', reason=redact('done'), at=SERVICE_MOMENT
    )


def create_review_run() -> ReviewRunRecord:
    return ReviewRunRecord(
        run_id=REVIEW_RUN,
        slug=SERVICE_SLUG,
        scope='branch',
        base='main',
        head='abc1234',
        depth='standard',
        emphasis='balanced',
        weights={'merge-vader': 1.0},
        personas=('merge-vader',),
        models={'merge-vader': None},
        created_at=SERVICE_MOMENT,
    )


def create_latest_review(
    decided: dict[str, Decision], *, undecided: Collection[str] = (), fixed: Collection[str] = ()
) -> LatestReview:
    keys = (*decided, *undecided)
    return LatestReview(
        run=create_review_run(),
        findings=tuple(create_finding(key) for key in keys),
        dispositions={key: create_decided(key, decision) for key, decision in decided.items()},
        outcomes={key: create_resolved(key) for key in fixed},
    )
