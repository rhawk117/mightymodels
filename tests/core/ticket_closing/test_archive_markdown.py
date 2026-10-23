from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import Slug, TaskId, redact
from mightymodels_core.ticket_closing import (
    ArchivedCommand,
    ArchivedDecision,
    ArchivedReview,
    ArchivedTask,
    ArchiveRecord,
    archive_markdown,
)
from mightymodels_core.tickets import Tracker

from .conftest import REVIEW_RUN, create_closing

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.ticket_closing.archive import CommandOutcome

RECORD_NAME = 'closing-subject-2.json'
DECISION_LIMIT = 4


@dataclass(slots=True, kw_only=True, frozen=True)
class ArchiveParts:
    tracker: Tracker
    tasks: dict[TaskId, ArchivedTask]
    verification: tuple[ArchivedCommand, ...]
    decisions: tuple[ArchivedDecision, ...]
    review: ArchivedReview | None


def create_command(key: str, outcome: CommandOutcome) -> ArchivedCommand:
    return ArchivedCommand(
        key=key, argv=('true',), expect_exit=0, outcome=outcome, head=None, digest=None
    )


def create_decisions(count: int) -> tuple[ArchivedDecision, ...]:
    return tuple(
        ArchivedDecision(text=redact(f'decision {index}'), origin='first-probe')
        for index in range(count)
    )


def create_review(reasons: Sequence[str]) -> ArchivedReview:
    return ArchivedReview(
        run=REVIEW_RUN,
        depth='standard',
        findings=3,
        by_decision={'fix': ('MV-1', 'MV-2'), 'wontfix': ('MV-3',)},
        reasons={f'MV-{index}': redact(reason) for index, reason in enumerate(reasons, start=1)},
    )


def create_record(parts: ArchiveParts) -> ArchiveRecord:
    return ArchiveRecord(
        slug=Slug('closing-subject'),
        tracker=parts.tracker,
        summary=redact('a summary'),
        investigations=(),
        closing=create_closing('Retry queue drains'),
        tasks=parts.tasks,
        verification=parts.verification,
        decisions=parts.decisions,
        review=parts.review,
    )


def create_parts(
    *,
    tracker: Tracker | None = None,
    decisions: tuple[ArchivedDecision, ...] = (),
    review: ArchivedReview | None = None,
) -> ArchiveParts:
    return ArchiveParts(
        tracker=tracker or Tracker(issue=42, jira=None),
        tasks={
            TaskId('T1'): ArchivedTask(status='verified', attempts={'engineer': 1}),
            TaskId('C1'): ArchivedTask(status='verified', attempts={'engineer': 1, 'architect': 1}),
        },
        verification=(create_command('T1.AC-1', 'pass'), create_command('T1.AC-2', 'fail')),
        decisions=decisions,
        review=review,
    )


def decision_limit_cases() -> pytest.MarkDecorator:
    cases = [
        pytest.param(0, 4, id='no-ledger'),
        pytest.param(2, 2, id='ledger-below-limit'),
        pytest.param(4, 0, id='ledger-at-limit'),
        pytest.param(5, 0, id='ledger-over-limit'),
    ]
    return pytest.mark.parametrize(('ledger_count', 'reason_count'), cases)


class TestArchiveMarkdown:
    shipped_parts = (
        'shipped: Retry queue drains',
        'PR: https://example.test/pull/7',
        'tracker: #42 ABC-7',
        'pruned: 2026-01-02',
        'head: abc1234',
    )

    @pytest.fixture
    def full_parts(self) -> ArchiveParts:
        return create_parts(
            tracker=Tracker(issue=42, jira='ABC-7'),
            decisions=create_decisions(1),
            review=create_review(['worth doing', 'later']),
        )

    @pytest.fixture
    def empty_parts(self) -> ArchiveParts:
        return ArchiveParts(
            tracker=Tracker(issue=None, jira=None),
            tasks={},
            verification=(),
            decisions=(),
            review=None,
        )

    @pytest.fixture
    def never_run_parts(self) -> ArchiveParts:
        parts = create_parts()
        return ArchiveParts(
            tracker=parts.tracker,
            tasks=parts.tasks,
            verification=(create_command('T1.AC-1', 'never-run'),),
            decisions=(),
            review=None,
        )

    def render(self, parts: ArchiveParts, decision_limit: int = DECISION_LIMIT) -> list[str]:
        text = archive_markdown(create_record(parts), RECORD_NAME, decision_limit)
        assert text.endswith('\n')
        return text.splitlines()

    def test_archive_follows_the_section_order_line_by_line(self, full_parts: ArchiveParts) -> None:
        assert self.render(full_parts) == [
            '# closing-subject',
            ' · '.join(self.shipped_parts),
            'tasks: T1 (engineer 1); C1 (engineer 1, architect 1)',
            'checks: 2 contract commands, 1 passing at last run; not passing: T1.AC-2',
            'review: run 20260506-070809 (standard), 3 findings; fix MV-1, MV-2; wontfix MV-3',
            'decisions:',
            '- decision 0 (first-probe)',
            '- review MV-1: worth doing',
            '- review MV-2: later',
            'gotchas:',
            '- first gotcha',
            '- second gotcha',
            'details: archives/closing-subject-2.json',
        ]

    def test_empty_parts_print_none_recorded(self, empty_parts: ArchiveParts) -> None:
        lines = self.render(empty_parts)
        assert lines[1].split(' · ')[2] == 'tracker: none'
        assert lines[2:7] == [
            'tasks: none recorded',
            'checks: 0 contract commands, 0 passing at last run',
            'review: none',
            'decisions:',
            '- none recorded',
        ]

    def test_never_run_command_is_not_passing(self, never_run_parts: ArchiveParts) -> None:
        assert self.render(never_run_parts)[3].endswith(
            '0 passing at last run; not passing: T1.AC-1'
        )

    @decision_limit_cases()
    def test_decisions_stay_within_the_limit(self, ledger_count: int, reason_count: int) -> None:
        parts = create_parts(
            decisions=create_decisions(ledger_count),
            review=create_review(['reason'] * 6),
        )
        lines = self.render(parts)
        shown = lines[lines.index('decisions:') + 1 : lines.index('gotchas:')]
        assert len([line for line in shown if line.startswith('- review ')]) == reason_count
        assert len(shown) == max(ledger_count, DECISION_LIMIT)
