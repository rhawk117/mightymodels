import pytest
from mightymodels_core.workspace import (
    TicketFile,
    TicketFileSyntaxError,
    TicketFileTypeError,
    parse_ticket_file,
)

from .conftest import SyntaxRefusal, TypeRefusal


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
            name='duplicate-key-spelled-with-a-space-before-the-colon',
            source='task: t\ntask : evil\n',
            line=2,
            reason='a key holds no whitespace',
        ),
        SyntaxRefusal(
            name='duplicate-key-spelled-with-quotes',
            source='task: t\n"task": evil\n',
            line=2,
            reason='a key holds no whitespace and no quote',
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
            name='multi-line-double-quoted',
            source='task: t\nsummary: "a\n# hidden\n  b: c"\n',
            line=2,
            reason='unsupported YAML syntax',
        ),
        SyntaxRefusal(
            name='multi-line-double-quoted-list-item',
            source='task: t\nfiles:\n  - "a\n# x\n  b"\n',
            line=3,
            reason='unsupported YAML syntax',
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
            name='unterminated-quote',
            source='a: 1\nb: "open\n',
            line=2,
            reason='unsupported YAML syntax',
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


def ticket_unreadable_character_cases() -> pytest.MarkDecorator:
    cases = [
        SyntaxRefusal(
            name='line-separator-smuggling-a-duplicate-key',
            source='task: t\nsummary: a\u2028task: evil\n',
            line=2,
            reason='U+2028',
        ),
        SyntaxRefusal(
            name='paragraph-separator', source='task: a\u2029b\n', line=1, reason='U+2029'
        ),
        SyntaxRefusal(
            name='next-line-in-a-comment', source='task: a\n# x\x85y\n', line=2, reason='U+0085'
        ),
        SyntaxRefusal(
            name='form-feed-in-a-value',
            source='task: a\nsummary: b\x0cc\n',
            line=2,
            reason='U+000C',
        ),
        SyntaxRefusal(name='delete', source='task: a\x7f\n', line=1, reason='U+007F'),
        SyntaxRefusal(
            name='c1-control', source='task: a\nsummary: \x9f\n', line=2, reason='U+009F'
        ),
        SyntaxRefusal(
            name='control-character-in-a-blank-line',
            source='task: a\n\x0c\n',
            line=2,
            reason='U+000C',
        ),
        SyntaxRefusal(name='noncharacter', source='task: a\n\n\ufffe\n', line=3, reason='U+FFFE'),
    ]
    return pytest.mark.parametrize('refusal', [case.param for case in cases])


def ticket_unknown_key_cases() -> pytest.MarkDecorator:
    cases = [
        TypeRefusal(
            name='top-level',
            source='task: t\nbogus: 1\nhandoff-context:\n  wat: x\n',
            key_path='$.bogus',
            line=2,
        ),
        TypeRefusal(
            name='handoff-context',
            source='task: t\nhandoff-context:\n  scope: med\n  wat: x\n',
            key_path='$.handoff-context.wat',
            line=4,
        ),
        TypeRefusal(
            name='companion-docs',
            source='companion-docs:\n  issue-number: 4\n  ticket-url: x\n',
            key_path='$.companion-docs.ticket-url',
            line=3,
        ),
    ]
    return pytest.mark.parametrize('refusal', [case.param for case in cases])


class TestRefuseTicketFile:
    @ticket_syntax_refusal_cases()
    def test_text_outside_the_subset_is_refused_with_its_line(self, refusal: SyntaxRefusal) -> None:
        issue = parse_ticket_file(refusal.source)

        assert isinstance(issue, TicketFileSyntaxError)
        assert issue.line == refusal.line
        assert refusal.reason in issue.reason

    @ticket_unreadable_character_cases()
    def test_a_line_break_or_control_character_pyyaml_reads_differently_is_refused_with_its_line(
        self, refusal: SyntaxRefusal
    ) -> None:
        issue = parse_ticket_file(refusal.source)

        assert isinstance(issue, TicketFileSyntaxError)
        assert issue.line == refusal.line
        assert refusal.reason in issue.reason

    @ticket_unknown_key_cases()
    def test_a_key_the_ticket_does_not_know_is_refused_with_its_key_path_and_line(
        self, refusal: TypeRefusal
    ) -> None:
        issue = parse_ticket_file(refusal.source)

        assert isinstance(issue, TicketFileTypeError)
        assert issue.key_path == refusal.key_path
        assert issue.line == refusal.line

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
