"""A real sqlite database with a ticket seeded in two repositories, and a SnapshotRead over each."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import ConnectionOptions, open_database
from mightymodels_core.edge import create_database_spec
from mightymodels_core.git import GitNoAnswerError
from mightymodels_core.primitives import RepositoryKey, Slug
from mightymodels_core.snapshot import RepositoryFacts
from mightymodels_core.units_of_work import SnapshotRead, TaskWork

from tests.core.primitives.clock import create_fake_clock
from tests.core.snapshot.snapshot_builders import (
    MOMENT,
    OTHER_SUMMARY,
    REPOSITORY_FACTS,
    create_section,
    seed_investigation,
    seed_review,
    seed_ticket,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RunId


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
def repository_facts() -> RepositoryFacts:
    return REPOSITORY_FACTS


@pytest.fixture
def investigation(database: Database, repository_key: RepositoryKey, clock: Clock) -> Slug:
    return seed_investigation(database, repository_key, clock)


@pytest.fixture
def seeded(
    database: Database,
    repository_key: RepositoryKey,
    clock: Clock,
    slug: Slug,
    investigation: Slug,
) -> Slug:
    return seed_ticket(database, repository_key, clock, slug, investigation)


@pytest.fixture
def reviewed(
    database: Database, repository_key: RepositoryKey, clock: Clock, seeded: Slug
) -> RunId:
    return seed_review(database, repository_key, clock, seeded)


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
