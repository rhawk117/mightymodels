from datetime import UTC, datetime

import pytest
from mightymodels_core.primitives import RunId, Slug, TaskId
from mightymodels_core.snapshot import (
    CheckState,
    FailedAttempt,
    LedgerLine,
    PassingCommand,
    RepositoryState,
    ReviewDecision,
    ReviewState,
    SnapshotRecord,
    TaskState,
    TicketSummary,
    snapshot_markdown,
)
from mightymodels_core.tickets import Tracker


def create_record(repository: RepositoryState, *, warnings: tuple[str, ...] = ()) -> SnapshotRecord:
    return SnapshotRecord(
        slug=Slug('add-widget'),
        generated_at=datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC),
        ticket=TicketSummary(
            summary='add the widget',
            status='in-progress',
            scope='med',
            tracker=Tracker(issue=None, jira=None),
        ),
        repository=repository,
        tasks=(),
        checks=(),
        works=(),
        decisions=(),
        open_questions=(),
        do_not_retry=(),
        review=None,
        warnings=warnings,
    )


def section_line_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'line',
        [
            '- T1 blocked (engineer 2 | a wall)',
            '- T2 not started',
            '- T1.AC-1 never-run',
            '- T1.AC-2: `pytest -q`',
            '- use sqlite [doc] (cache e1)',
            '- which size (cache e2)',
            '- T1 blocked at aaaaaaaaaaaa: a wall',
            '- run 20260506-070809 (standard) at aaaaaaaaaaaa: 3 findings',
            '- undecided: F2',
            '- remediation open: F1, F3',
            '- F4 defer: later',
            '- F5 dismiss: no reason',
            '- git was not consulted: it did not answer',
        ],
    )


class TestEmptySnapshot:
    @pytest.fixture
    def markdown(self) -> str:
        repository = RepositoryState(branch=None, head=None, dirty_count=None, dirty=())
        return snapshot_markdown(create_record(repository))

    def test_header_names_the_detached_unknown_repository(self, markdown: str) -> None:
        assert markdown.splitlines()[:5] == [
            '# Snapshot for add-widget',
            '',
            'Generated 2026-05-06T07:08:09+00:00 from durable files only.',
            'Ticket: add the widget (status in-progress).',
            'Repository: detached at unknown; tree unknown.',
        ]

    def test_each_empty_section_says_so_in_one_line(self, markdown: str) -> None:
        assert markdown.splitlines()[5:] == [
            '',
            '## Tasks',
            '',
            '- none started',
            '',
            '## Checks at HEAD',
            '',
            '- no contract',
            '',
            '## Works',
            '',
            '- no passing command yet',
            '',
            '## Decisions',
            '',
            '- none recorded',
            '',
            '## Open questions',
            '',
            '- none recorded',
            '',
            '## Do not retry',
            '',
            '- no failed attempt recorded',
            '',
            '## Review',
            '',
            '- no review run',
        ]

    def test_markdown_ends_with_one_newline_and_has_no_warnings_section(
        self, markdown: str
    ) -> None:
        assert markdown.endswith('run\n')
        assert '## Warnings' not in markdown


class TestFilledSnapshot:
    @pytest.fixture
    def markdown(self) -> str:
        repository = RepositoryState(
            branch='feat/widget', head='a' * 40, dirty_count=2, dirty=('src/a.py', 'src/b.py')
        )
        record = SnapshotRecord(
            slug=Slug('add-widget'),
            generated_at=datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC),
            ticket=TicketSummary(
                summary='add the widget',
                status='in-progress',
                scope='med',
                tracker=Tracker(issue=None, jira=None),
            ),
            repository=repository,
            tasks=(
                TaskState(
                    task=TaskId('T1'),
                    status='blocked',
                    attempts={'engineer': 2},
                    reasons=('a wall',),
                ),
                TaskState(task=TaskId('T2'), status='not started', attempts={}, reasons=()),
            ),
            checks=(CheckState(key='T1.AC-1', state='never-run'),),
            works=(PassingCommand(key='T1.AC-2', argv=('pytest', '-q')),),
            decisions=(
                LedgerLine(kind='decision', text='use sqlite', cite='doc', origin='cache e1'),
            ),
            open_questions=(
                LedgerLine(kind='open', text='which size', cite=None, origin='cache e2'),
            ),
            do_not_retry=(
                FailedAttempt(
                    task=TaskId('T1'),
                    to='blocked',
                    reason='a wall',
                    head='aaaaaaaaaaaa',
                    at=datetime(2026, 5, 6, tzinfo=UTC),
                ),
            ),
            review=ReviewState(
                run=RunId('20260506-070809'),
                depth='standard',
                head='aaaaaaaaaaaa',
                findings=3,
                undecided=('F2',),
                remediation_open=('F1', 'F3'),
                decisions=(
                    ReviewDecision(finding='F4', decision='defer', reason='later'),
                    ReviewDecision(finding='F5', decision='dismiss', reason=''),
                ),
            ),
            warnings=('git was not consulted: it did not answer',),
        )
        return snapshot_markdown(record)

    def test_header_lists_the_dirty_paths(self, markdown: str) -> None:
        lines = markdown.splitlines()

        assert lines[4] == f'Repository: feat/widget at {"a" * 12}; tree 2 changed.'
        assert lines[5:7] == ['- changed: src/a.py', '- changed: src/b.py']

    @section_line_cases()
    def test_section_line_is_worded_from_the_record(self, markdown: str, line: str) -> None:
        assert line in markdown.splitlines()

    def test_warnings_come_last(self, markdown: str) -> None:
        assert markdown.splitlines()[-3:-1] == ['## Warnings', '']
