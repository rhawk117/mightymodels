from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.workspace import (
    CompanionDocsFile,
    HandoffContextFile,
    TicketFile,
    TicketFileSyntaxError,
    TicketFileTypeError,
    parse_ticket_file,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet


@dataclass(slots=True, kw_only=True, frozen=True)
class SyntaxRefusal:
    name: str
    source: str
    line: int
    reason: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


@dataclass(slots=True, kw_only=True, frozen=True)
class TypeRefusal:
    name: str
    source: str
    key_path: str
    line: int | None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def ticket_syntax_refusal_cases() -> pytest.MarkDecorator:
    cases = [
        SyntaxRefusal(
            name='odd-indent', source='a: 1\n b: 2\n', line=2, reason='multiple of two spaces'
        ),
        SyntaxRefusal(
            name='tab-alone', source='a:\n\tb: 1\n', line=2, reason='indentation holds a tab'
        ),
        SyntaxRefusal(
            name='tab-after-spaces',
            source='a:\n  \tb: 1\n',
            line=2,
            reason='indentation holds a tab',
        ),
        SyntaxRefusal(
            name='no-break-space',
            source='a:\n\xa0b: 1\n',
            line=2,
            reason='indentation holds U+00A0',
        ),
        SyntaxRefusal(
            name='em-space', source='a:\n\u2003b: 1\n', line=2, reason='indentation holds U+2003'
        ),
        SyntaxRefusal(
            name='form-feed', source='a:\n\x0cb: 1\n', line=2, reason='indentation holds U+000C'
        ),
        SyntaxRefusal(
            name='duplicate-key', source='a: 1\nb: 2\na: 3\n', line=3, reason='duplicate key a'
        ),
        SyntaxRefusal(
            name='duplicate-nested-key',
            source='a:\n  b: 1\n  b: 2\n',
            line=3,
            reason='duplicate key b',
        ),
        SyntaxRefusal(
            name='flow-mapping', source='a: {b: 1}\n', line=1, reason='unsupported YAML syntax'
        ),
        SyntaxRefusal(
            name='flow-sequence', source='a: [1, 2]\n', line=1, reason='unsupported YAML syntax'
        ),
        SyntaxRefusal(
            name='anchor', source='a: &anchor\n', line=1, reason='unsupported YAML syntax'
        ),
        SyntaxRefusal(
            name='single-quoted', source="a: 'x'\n", line=1, reason='unsupported YAML syntax'
        ),
        SyntaxRefusal(
            name='block-scalar', source='a: |\n  x\n', line=1, reason='unsupported YAML syntax'
        ),
        SyntaxRefusal(
            name='item-flow-sequence',
            source='a:\n  - [1]\n',
            line=2,
            reason='unsupported YAML syntax',
        ),
        SyntaxRefusal(name='no-key', source='just words\n', line=1, reason='expected "key: value"'),
        SyntaxRefusal(
            name='top-level-list', source='- a\n- b\n', line=1, reason='indented under its key'
        ),
        SyntaxRefusal(
            name='unterminated-quote', source='a: 1\nb: "open\n', line=2, reason='quoted scalar'
        ),
        SyntaxRefusal(
            name='indent-after-scalar', source='a: 1\n  b: 2\n', line=2, reason='not allowed'
        ),
    ]
    return pytest.mark.parametrize('refusal', [case.param for case in cases])


def ticket_type_refusal_cases() -> pytest.MarkDecorator:
    cases = [
        TypeRefusal(
            name='scope-outside-the-literal',
            source='task: "t"\nhandoff-context:\n  scope: huge\n',
            key_path='$.handoff-context.scope',
            line=3,
        ),
        TypeRefusal(
            name='flag-as-text',
            source='handoff-context:\n  plan-first: maybe\n',
            key_path='$.handoff-context.plan-first',
            line=2,
        ),
        TypeRefusal(
            name='issue-number-as-text',
            source='companion-docs:\n  issue-number: seven\n',
            key_path='$.companion-docs.issue-number',
            line=2,
        ),
        TypeRefusal(
            name='context-as-text',
            source='context: one line\n',
            key_path='$.context',
            line=1,
        ),
        TypeRefusal(
            name='list-item-as-number',
            source='context:\n  - fine\n  - 7\n',
            key_path='$.context[1]',
            line=3,
        ),
        TypeRefusal(
            name='model-as-number',
            source='subagent-models:\n  engineer: 7\n',
            key_path='$.subagent-models[...]',
            line=1,
        ),
    ]
    return pytest.mark.parametrize('refusal', [case.param for case in cases])


def ticket_bool_word_cases() -> pytest.MarkDecorator:
    cases = [
        TypeRefusal(name='yes', source='task: yes\n', key_path='$.task', line=1),
        TypeRefusal(name='no', source='task: no\n', key_path='$.task', line=1),
        TypeRefusal(
            name='on-nested',
            source='task: "t"\nhandoff-context:\n  branch-name: on\n',
            key_path='$.handoff-context.branch-name',
            line=3,
        ),
        TypeRefusal(
            name='off-in-a-list',
            source='context:\n  - fine\n  - off\n',
            key_path='$.context[1]',
            line=3,
        ),
        TypeRefusal(
            name='yes-jira-key',
            source='companion-docs:\n  jira-key: yes\n',
            key_path='$.companion-docs.jira-key',
            line=2,
        ),
    ]
    return pytest.mark.parametrize('refusal', [case.param for case in cases])


def ticket_blank_line_refusal_cases() -> pytest.MarkDecorator:
    cases = [
        SyntaxRefusal(
            name='tab-in-a-blank-line',
            source='task: a\n\t\nsummary: b\n',
            line=2,
            reason='indentation holds a tab',
        ),
        SyntaxRefusal(
            name='tab-in-a-comment-line',
            source='task: a\n\t# note\nsummary: b\n',
            line=2,
            reason='indentation holds a tab',
        ),
        SyntaxRefusal(
            name='no-break-space-in-a-blank-line',
            source='task: a\n\xa0\nsummary: b\n',
            line=2,
            reason='indentation holds U+00A0',
        ),
        SyntaxRefusal(
            name='no-break-space-in-a-comment-line',
            source='task: a\n\xa0# note\nsummary: b\n',
            line=2,
            reason='indentation holds U+00A0',
        ),
    ]
    return pytest.mark.parametrize('refusal', [case.param for case in cases])


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

    def test_a_key_the_ticket_does_not_know_is_ignored(self) -> None:
        assert parse_ticket_file('task: a\nreference-urls:\n') == TicketFile(task='a')

    @ticket_line_end_cases()
    def test_a_carriage_return_ends_a_line_with_or_without_a_newline_after_it(
        self, source: str
    ) -> None:
        assert parse_ticket_file(source) == TicketFile(task='a', summary='b')

    @ticket_blank_line_refusal_cases()
    def test_a_tab_or_no_break_space_before_a_blank_or_comment_line_is_refused_with_its_line(
        self, refusal: SyntaxRefusal
    ) -> None:
        issue = parse_ticket_file(refusal.source)

        assert isinstance(issue, TicketFileSyntaxError)
        assert issue.line == refusal.line
        assert refusal.reason in issue.reason

    @pytest.mark.parametrize(
        ('source', 'task'),
        [
            pytest.param('task: x\ty\n', 'x\ty', id='tab-inside-a-value'),
            pytest.param('task: x\xa0y\n', 'x\xa0y', id='no-break-space-inside-a-value'),
        ],
    )
    def test_a_character_inside_a_value_is_kept_in_the_value(self, source: str, task: str) -> None:
        assert parse_ticket_file(source) == TicketFile(task=task)


class TestRefuseTicketFile:
    @ticket_syntax_refusal_cases()
    def test_text_outside_the_subset_is_refused_with_its_line(self, refusal: SyntaxRefusal) -> None:
        issue = parse_ticket_file(refusal.source)

        assert isinstance(issue, TicketFileSyntaxError)
        assert issue.line == refusal.line
        assert refusal.reason in issue.reason

    @ticket_type_refusal_cases()
    def test_a_value_of_the_wrong_type_is_refused_with_its_key_path(
        self, refusal: TypeRefusal
    ) -> None:
        issue = parse_ticket_file(refusal.source)

        assert isinstance(issue, TicketFileTypeError)
        assert issue.key_path == refusal.key_path
        assert issue.line == refusal.line
        assert refusal.key_path in str(issue)

    @ticket_bool_word_cases()
    def test_an_unquoted_boolean_word_in_a_string_field_is_refused_with_line_and_key_path(
        self, refusal: TypeRefusal
    ) -> None:
        issue = parse_ticket_file(refusal.source)

        assert isinstance(issue, TicketFileTypeError)
        assert issue.key_path == refusal.key_path
        assert issue.line == refusal.line
        assert f'ticket.yml:{refusal.line}: {refusal.key_path}' in str(issue)

    def test_a_refused_file_returns_no_partial_ticket(self) -> None:
        source = 'task: "t"\nsummary: "s"\nhandoff-context:\n  plan-first: maybe\n'

        result = parse_ticket_file(source)

        assert isinstance(result, TicketFileTypeError)
        assert not isinstance(result, TicketFile)
