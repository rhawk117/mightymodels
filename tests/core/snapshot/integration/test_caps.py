from dataclasses import dataclass
from operator import attrgetter
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.investigations import AddRequest, IncomingEntry
from mightymodels_core.primitives import TaskId
from mightymodels_core.reviews import IncomingDisposition
from mightymodels_core.snapshot import SnapshotRequest
from mightymodels_core.tasks import MarkRequest
from mightymodels_core.tasks import StartRequest as TaskStartRequest

from tests.core.snapshot.snapshot_builders import HEAD, create_defect, create_receipt

if TYPE_CHECKING:
    from mightymodels_core.primitives import RunId, Slug
    from mightymodels_core.snapshot import RepositoryFacts, SnapshotRecord
    from mightymodels_core.units_of_work import (
        InvestigationWork,
        ReviewWork,
        SnapshotRead,
        TaskWork,
    )

CAPPED_SECTIONS = ('works', 'decisions', 'open_questions', 'review.decisions', 'do_not_retry')
UNCAPPED_LIMIT = 10
CAP = 1


def snapshot_section_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('section', CAPPED_SECTIONS)


@dataclass(slots=True, kw_only=True, frozen=True)
class CrowdedTicket:
    ledger: Slug
    slug: Slug
    run: RunId


@pytest.fixture
def crowded_ledger(investigation_work: InvestigationWork, investigation: Slug) -> Slug:
    entries = [
        IncomingEntry(kind='decision', text='use wal mode', source='user'),
        IncomingEntry(kind='open', text='which retention', source='primary'),
    ]
    with investigation_work.write() as unit:
        unit.investigations.add(investigation, AddRequest(round=2, entries=entries, head=HEAD))
    return investigation


@pytest.fixture
def crowded_tasks(task_work: TaskWork, seeded: Slug) -> Slug:
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
    with task_work.write() as unit:
        unit.contracts.record(seeded, receipts)
        unit.tasks.start(seeded, start)
        unit.tasks.mark(seeded, MarkRequest(task_key=TaskId('T2'), to='blocked', reason='a wall'))
    return seeded


@pytest.fixture
def crowded_review(review_work: ReviewWork, reviewed: RunId) -> RunId:
    with review_work.write() as unit:
        added = unit.reviews.add_findings(reviewed, [create_defect('MV-3')])
        decided = {added.changed[0].key: IncomingDisposition(decision='defer', reason='later')}
        unit.decisions.dispose(reviewed, decided, 'owner')
    return reviewed


@pytest.fixture
def crowded(crowded_ledger: Slug, crowded_tasks: Slug, crowded_review: RunId) -> CrowdedTicket:
    return CrowdedTicket(ledger=crowded_ledger, slug=crowded_tasks, run=crowded_review)


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
