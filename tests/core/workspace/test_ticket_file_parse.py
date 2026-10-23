import pytest
from mightymodels_core.workspace import (
    CompanionDocsFile,
    HandoffContextFile,
    TicketFile,
    parse_ticket_file,
)


def ticket_blank_line_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'source',
        [
            pytest.param('task: t\n\t\n# c\n', id='tab-in-a-blank-line'),
            pytest.param('task: t\n\t# c\n', id='tab-in-a-comment-line'),
            pytest.param('task: t\n\xa0\n# c\n', id='no-break-space-in-a-blank-line'),
            pytest.param('task: t\n\xa0# c\n', id='no-break-space-in-a-comment-line'),
        ],
    )


def ticket_line_end_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'source',
        [
            pytest.param('task: a\r\nsummary: b\r\n', id='crlf-line-ends'),
            pytest.param('task: a\rsummary: b\r', id='cr-line-ends'),
        ],
    )


class TestParseTicketFile:
    full_source = (
        '# a ticket\n'
        'task: "retry-queue"   # the slug\n'
        'summary: "Retry the queue"\n'
        'triaged-at: "2026-10-19T13:42:35+00:00"\n'
        'companion-docs:\n'
        '  issue-number: 42\n'
        '  jira-key:\n'
        'subagent-models:\n'
        '  primary-agent:\n'
        '  engineer: "sonnet"\n'
        'handoff-context:\n'
        '  scope: med\n'
        '  plan-first: true\n'
        '  branch-name: feat/retry\n'
        '  auto-escalate: false\n'
        '  worktrees-okay: false\n'
        'context:\n'
        '  - "a: b"\n'
        '  - plain # trailing\n'
        '\n'
        'investigations:\n'
        '  - "20261019-inventory"\n'
    )

    def test_reads_every_key_of_a_ticket(self) -> None:
        assert parse_ticket_file(self.full_source) == TicketFile(
            task='retry-queue',
            summary='Retry the queue',
            triaged_at='2026-10-19T13:42:35+00:00',
            companion_docs=CompanionDocsFile(issue_number=42, jira_key=None),
            subagent_models={'primary-agent': None, 'engineer': 'sonnet'},
            handoff_context=HandoffContextFile(
                scope='med',
                plan_first=True,
                branch_name='feat/retry',
                auto_escalate=False,
                worktrees_okay=False,
            ),
            context=('a: b', 'plain'),
            investigations=('20261019-inventory',),
        )

    def test_a_file_without_keys_is_an_empty_ticket(self) -> None:
        assert parse_ticket_file('# nothing yet\n\n') == TicketFile()

    def test_reference_urls_are_a_list_of_text(self) -> None:
        source = 'companion-docs:\n  reference-urls:\n    - https://example.com/a\n    - other\n'

        assert parse_ticket_file(source) == TicketFile(
            companion_docs=CompanionDocsFile(reference_urls=('https://example.com/a', 'other'))
        )

    @ticket_line_end_cases()
    def test_a_carriage_return_ends_a_line_with_or_without_a_newline_after_it(
        self, source: str
    ) -> None:
        assert parse_ticket_file(source) == TicketFile(task='a', summary='b')

    @ticket_blank_line_cases()
    def test_a_blank_or_comment_line_holding_a_tab_or_no_break_space_is_skipped(
        self, source: str
    ) -> None:
        assert parse_ticket_file(source) == TicketFile(task='t')

    @pytest.mark.parametrize(
        ('source', 'task'),
        [
            pytest.param('task: x\ty\n', 'x\ty', id='tab-inside-a-value'),
            pytest.param('task: x\xa0y\n', 'x\xa0y', id='no-break-space-inside-a-value'),
            pytest.param('task: "a # b"\n', 'a # b', id='double-quoted-holding-a-hash'),
            pytest.param('task: "a" # note\n', 'a', id='double-quoted-with-a-trailing-comment'),
            pytest.param('task: "a\\"b"\n', 'a"b', id='double-quoted-holding-an-escaped-quote'),
        ],
    )
    def test_a_character_inside_a_value_is_kept_in_the_value(self, source: str, task: str) -> None:
        assert parse_ticket_file(source) == TicketFile(task=task)
