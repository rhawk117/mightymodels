from dataclasses import dataclass
from operator import attrgetter
from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.snapshot import SnapshotRequest

from tests.core.snapshot.snapshot_builders import (
    REPOSITORY_FACTS,
    open_crowded_snapshot,
    seed_crowded_ledger,
    seed_crowded_review,
    seed_crowded_tasks,
)

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RepositoryKey, RunId, Slug
    from mightymodels_core.snapshot import RepositoryFacts, SnapshotRecord
    from mightymodels_core.units_of_work import SnapshotRead

CAPPED_SECTIONS = ('works', 'decisions', 'open_questions', 'review.decisions', 'do_not_retry')
UNCAPPED_LIMIT = 10
CAP = 1


@dataclass(slots=True, kw_only=True, frozen=True)
class CrowdedTicket:
    ledger: Slug
    slug: Slug
    run: RunId


@pytest.fixture
def crowded_ledger(
    database: Database, repository_key: RepositoryKey, clock: Clock, investigation: Slug
) -> Slug:
    return seed_crowded_ledger(database, repository_key, clock, investigation)


@pytest.fixture
def crowded_tasks(
    database: Database, repository_key: RepositoryKey, clock: Clock, seeded: Slug
) -> Slug:
    return seed_crowded_tasks(database, repository_key, clock, seeded)


@pytest.fixture
def crowded_review(
    database: Database, repository_key: RepositoryKey, clock: Clock, reviewed: RunId
) -> RunId:
    return seed_crowded_review(database, repository_key, clock, reviewed)


@pytest.fixture
def crowded(crowded_ledger: Slug, crowded_tasks: Slug, crowded_review: RunId) -> CrowdedTicket:
    return CrowdedTicket(ledger=crowded_ledger, slug=crowded_tasks, run=crowded_review)


@pytest.mark.usefixtures('crowded')
class TestSnapshotCaps:
    def take_snapshot(
        self, read: SnapshotRead, slug: Slug, repository: RepositoryFacts, limit: int
    ) -> SnapshotRecord:
        request = SnapshotRequest(slug=slug, repository=repository, limit=limit)
        with read.read() as unit:
            return unit.snapshots.take(request)

    def size_of(self, record: SnapshotRecord, section: str) -> int:
        return len(attrgetter(section)(record))

    def assert_capped(
        self, read: SnapshotRead, slug: Slug, repository: RepositoryFacts, section: str, full: int
    ) -> None:
        uncapped = self.take_snapshot(read, slug, repository, limit=UNCAPPED_LIMIT)
        capped = self.take_snapshot(read, slug, repository, limit=CAP)

        assert self.size_of(uncapped, section) == full
        assert self.size_of(capped, section) == CAP

    def test_limit_caps_the_works(
        self, snapshot_read: SnapshotRead, slug: Slug, repository_facts: RepositoryFacts
    ) -> None:
        self.assert_capped(snapshot_read, slug, repository_facts, 'works', full=3)

    def test_limit_caps_the_decisions(
        self, snapshot_read: SnapshotRead, slug: Slug, repository_facts: RepositoryFacts
    ) -> None:
        self.assert_capped(snapshot_read, slug, repository_facts, 'decisions', full=2)

    def test_limit_caps_the_open_questions(
        self, snapshot_read: SnapshotRead, slug: Slug, repository_facts: RepositoryFacts
    ) -> None:
        self.assert_capped(snapshot_read, slug, repository_facts, 'open_questions', full=2)

    def test_limit_caps_the_review_decisions(
        self, snapshot_read: SnapshotRead, slug: Slug, repository_facts: RepositoryFacts
    ) -> None:
        self.assert_capped(snapshot_read, slug, repository_facts, 'review.decisions', full=2)

    def test_limit_caps_the_do_not_retry_attempts(
        self, snapshot_read: SnapshotRead, slug: Slug, repository_facts: RepositoryFacts
    ) -> None:
        self.assert_capped(snapshot_read, slug, repository_facts, 'do_not_retry', full=2)


class TestSnapshotLimitZero:
    sections = st.sampled_from(CAPPED_SECTIONS)
    repository = REPOSITORY_FACTS

    def take_limit_zero_snapshot(self, directory: Path) -> SnapshotRecord:
        with open_crowded_snapshot(directory) as crowded:
            request = SnapshotRequest(slug=crowded.slug, repository=self.repository, limit=0)
            with crowded.read.read() as unit:
                return unit.snapshots.take(request)

    @given(section=sections)
    @example(section='works')
    @example(section='decisions')
    @example(section='open_questions')
    @example(section='review.decisions')
    @example(section='do_not_retry')
    def test_limit_zero_keeps_no_line_of_any_capped_section(
        self, tmp_path_factory: pytest.TempPathFactory, section: str
    ) -> None:
        directory = tmp_path_factory.mktemp('crowded')

        record = self.take_limit_zero_snapshot(directory)

        assert len(attrgetter(section)(record)) == 0
