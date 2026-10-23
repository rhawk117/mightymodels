from typing import TYPE_CHECKING

import pytest
from mightymodels_core.snapshot import DEFAULT_LIMIT, SnapshotRequest, snapshot_markdown

if TYPE_CHECKING:
    from mightymodels_core.primitives import RunId, Slug
    from mightymodels_core.snapshot import RepositoryFacts, SnapshotRecord
    from mightymodels_core.units_of_work import SnapshotRead

SECTION_HEADINGS = [
    '## Tasks',
    '## Checks at HEAD',
    '## Works',
    '## Decisions',
    '## Open questions',
    '## Do not retry',
    '## Review',
]


def take_snapshot(
    read: SnapshotRead, slug: Slug, repository: RepositoryFacts, limit: int = DEFAULT_LIMIT
) -> SnapshotRecord:
    with read.read() as unit:
        return unit.snapshots.take(SnapshotRequest(slug=slug, repository=repository, limit=limit))


def headings_of(record: SnapshotRecord) -> list[str]:
    lines = snapshot_markdown(record).splitlines()
    return [line for line in lines if line.startswith('## ')]


@pytest.mark.integration
class TestSnapshotRead:
    def test_record_holds_the_generated_time_of_the_injected_clock(
        self, snapshot_read: SnapshotRead, seeded: Slug, repository_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, repository_facts)

        assert record.generated_at == snapshot_read.clock.now()

    def test_record_reads_the_entry_repository_rows(
        self,
        snapshot_read: SnapshotRead,
        other_snapshot_read: SnapshotRead,
        seeded: Slug,
        other_seeded: Slug,
        repository_facts: RepositoryFacts,
    ) -> None:
        own = take_snapshot(snapshot_read, seeded, repository_facts)
        other = take_snapshot(other_snapshot_read, other_seeded, repository_facts)

        assert own.ticket.summary == 'add the widget'
        assert other.ticket.summary == 'a ticket of the other repository'
        assert (len(own.tasks), len(other.tasks)) == (1, 0)

    def test_task_section_names_the_blocked_task_and_its_attempts(
        self, snapshot_read: SnapshotRead, seeded: Slug, repository_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, repository_facts)

        (task,) = record.tasks
        assert (task.task, task.status, dict(task.attempts)) == ('T1', 'blocked', {'engineer': 1})

    def test_checks_judge_each_receipt_at_the_head_the_adapter_passed(
        self, snapshot_read: SnapshotRead, seeded: Slug, repository_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, repository_facts)

        states = {check.key: check.state for check in record.checks}
        assert states == {
            'T1.AC-1': 'pass',
            'T1.AC-2': 'stale (fail at bbbbbbbbbbbb)',
            'T2.AC-1': 'never-run',
        }

    def test_works_lists_only_the_commands_whose_latest_receipt_passed(
        self, snapshot_read: SnapshotRead, seeded: Slug, repository_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, repository_facts)

        assert [command.key for command in record.works] == ['T1.AC-1']

    def test_do_not_retry_holds_the_blocked_move_with_its_reason(
        self, snapshot_read: SnapshotRead, seeded: Slug, repository_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, repository_facts)

        (attempt,) = record.do_not_retry
        assert (attempt.task, attempt.to, attempt.reason) == ('T1', 'blocked', 'a wall')

    def test_decisions_and_open_questions_come_from_the_linked_ledger(
        self, snapshot_read: SnapshotRead, seeded: Slug, repository_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, repository_facts)

        assert [line.text for line in record.decisions] == ['use sqlite']
        assert [line.text for line in record.open_questions] == ['which cache size']


@pytest.mark.integration
class TestSnapshotReadLimitsAndHeadings:
    def test_dirty_paths_are_cut_to_the_limit_and_the_count_stays_whole(
        self, snapshot_read: SnapshotRead, seeded: Slug, repository_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, repository_facts, limit=2)

        assert record.repository.dirty == ('src/a.py', 'src/b.py')
        assert record.repository.dirty_count == 3

    def test_review_state_counts_the_undecided_findings(
        self,
        snapshot_read: SnapshotRead,
        reviewed: RunId,
        slug: Slug,
        repository_facts: RepositoryFacts,
    ) -> None:
        record = take_snapshot(snapshot_read, slug, repository_facts)

        assert record.review is not None
        assert record.review.run == reviewed
        assert record.review.findings == 2
        assert len(record.review.undecided) == 1
        assert [decision.decision for decision in record.review.decisions] == ['defer']

    def test_git_refusal_becomes_a_warning_and_the_tree_is_unknown(
        self, snapshot_read: SnapshotRead, seeded: Slug, refused_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, refused_facts)

        assert record.repository.dirty_count is None
        assert [warning.startswith('git was not consulted') for warning in record.warnings] == [
            True
        ]

    @pytest.mark.usefixtures('reviewed')
    def test_rendered_headings_follow_the_old_snapshot_order_without_answers_or_subagents(
        self,
        snapshot_read: SnapshotRead,
        slug: Slug,
        refused_facts: RepositoryFacts,
    ) -> None:
        record = take_snapshot(snapshot_read, slug, refused_facts)

        assert headings_of(record) == [*SECTION_HEADINGS, '## Warnings']

    def test_rendered_headings_leave_out_warnings_when_there_are_none(
        self, snapshot_read: SnapshotRead, seeded: Slug, repository_facts: RepositoryFacts
    ) -> None:
        record = take_snapshot(snapshot_read, seeded, repository_facts)

        assert headings_of(record) == SECTION_HEADINGS
