from operator import attrgetter
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.snapshot import SnapshotRequest

if TYPE_CHECKING:
    from mightymodels_core.primitives import Slug
    from mightymodels_core.snapshot import RepositoryFacts, SnapshotRecord
    from mightymodels_core.units_of_work import SnapshotRead

CAPPED_SECTIONS = ('works', 'decisions', 'open_questions', 'review.decisions', 'do_not_retry')
UNCAPPED_LIMIT = 10
CAP = 1


def snapshot_section_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('section', CAPPED_SECTIONS)


@pytest.mark.integration
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

    @snapshot_section_cases()
    def test_limit_zero_keeps_no_line_of_any_capped_section(
        self,
        snapshot_read: SnapshotRead,
        slug: Slug,
        repository_facts: RepositoryFacts,
        section: str,
    ) -> None:
        record = self.take_snapshot(snapshot_read, slug, repository_facts, limit=0)

        assert self.size_of(record, section) == 0
