from dataclasses import dataclass

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.workspace import (
    TicketFile,
    TicketFileSyntaxError,
    TicketFileTypeError,
    parse_ticket_file,
)

from tests.core.workspace.workspace_builders import (
    REFUSED_CHARACTERS,
    SyntaxRefusal,
    TypeRefusal,
)

BOOLEAN_WORDS = tuple(
    spelling
    for word in ('yes', 'no', 'true', 'false', 'on', 'off')
    for spelling in (word, word.title(), word.upper())
)
INDENT_WHITESPACE = tuple(
    character
    for character in map(chr, range(0x3001))
    if character.isspace() and character not in ' \t\n\r'
)
LINE_SHAPES = ('summary: a{c}b', '# a{c}b', '{c}')


@dataclass(slots=True, kw_only=True, frozen=True)
class StringFieldPlacement:
    template: str
    key_path: str
    line: int

    def source_for(self, word: str) -> str:
        return self.template.format(word=word)


TOP_LEVEL_TASK = StringFieldPlacement(template='task: {word}\n', key_path='$.task', line=1)
BRANCH_NAME = StringFieldPlacement(
    template='task: "t"\nhandoff-context:\n  branch-name: {word}\n',
    key_path='$.handoff-context.branch-name',
    line=3,
)
CONTEXT_ITEM = StringFieldPlacement(
    template='context:\n  - fine\n  - {word}\n', key_path='$.context[1]', line=3
)
JIRA_KEY = StringFieldPlacement(
    template='companion-docs:\n  jira-key: {word}\n',
    key_path='$.companion-docs.jira-key',
    line=2,
)


def ticket_syntax_refusal_cases() -> pytest.MarkDecorator:
    cases = [
        SyntaxRefusal(
            name='odd-indent', source='a: 1\n b: 2\n', line=2, reason='multiple of two spaces'
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
    spaces = st.text(alphabet=' ')
    indent_whitespace = st.sampled_from(INDENT_WHITESPACE)
    refused_characters = REFUSED_CHARACTERS
    line_shapes = st.sampled_from(LINE_SHAPES)
    boolean_words = st.sampled_from(BOOLEAN_WORDS)
    string_field_placements = st.sampled_from((TOP_LEVEL_TASK, BRANCH_NAME, CONTEXT_ITEM, JIRA_KEY))

    @ticket_syntax_refusal_cases()
    def test_text_outside_the_subset_is_refused_with_its_line(self, refusal: SyntaxRefusal) -> None:
        issue = parse_ticket_file(refusal.source)

        assert isinstance(issue, TicketFileSyntaxError)
        assert issue.line == refusal.line
        assert refusal.reason in issue.reason

    @given(character=refused_characters, shape=line_shapes)
    @example(character='\u2028', shape='summary: a{c}b')
    @example(character='\u2029', shape='summary: a{c}b')
    @example(character='\x85', shape='# a{c}b')
    @example(character='\x0c', shape='summary: a{c}b')
    @example(character='\x7f', shape='summary: a{c}b')
    @example(character='\x9f', shape='summary: a{c}b')
    @example(character='\x0c', shape='{c}')
    @example(character='\ufffe', shape='{c}')
    def test_a_line_break_or_control_character_pyyaml_reads_differently_is_refused_with_its_line(
        self, character: str, shape: str
    ) -> None:
        line = shape.format(c=character)

        issue = parse_ticket_file(f'task: a\n{line}\n')

        assert isinstance(issue, TicketFileSyntaxError)
        assert issue.line == 2
        assert f'U+{ord(character):04X}' in issue.reason

    @given(spaces=spaces)
    @example(spaces='')
    @example(spaces='  ')
    def test_a_tab_in_the_indentation_is_refused_with_its_line(self, spaces: str) -> None:
        issue = parse_ticket_file(f'a:\n{spaces}\tb: 1\n')

        assert isinstance(issue, TicketFileSyntaxError)
        assert issue.line == 2
        assert 'indentation holds a tab' in issue.reason

    @given(spaces=spaces, character=indent_whitespace)
    @example(spaces='', character='\xa0')
    @example(spaces='', character='\u2003')
    @example(spaces='', character='\x0c')
    def test_other_whitespace_in_the_indentation_is_refused_with_its_code_point(
        self, spaces: str, character: str
    ) -> None:
        issue = parse_ticket_file(f'a:\n{spaces}{character}b: 1\n')

        assert isinstance(issue, TicketFileSyntaxError)
        assert issue.line == 2
        assert f'indentation holds U+{ord(character):04X}' in issue.reason

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

    @given(word=boolean_words, placement=string_field_placements)
    @example(word='yes', placement=TOP_LEVEL_TASK)
    @example(word='no', placement=TOP_LEVEL_TASK)
    @example(word='on', placement=BRANCH_NAME)
    @example(word='off', placement=CONTEXT_ITEM)
    @example(word='yes', placement=JIRA_KEY)
    def test_an_unquoted_boolean_word_in_a_string_field_is_refused_with_line_and_key_path(
        self, word: str, placement: StringFieldPlacement
    ) -> None:
        issue = parse_ticket_file(placement.source_for(word))

        assert isinstance(issue, TicketFileTypeError)
        assert issue.key_path == placement.key_path
        assert issue.line == placement.line
        assert f'ticket.yml:{placement.line}: {placement.key_path}' in str(issue)

    def test_a_refused_file_returns_no_partial_ticket(self) -> None:
        source = 'task: "t"\nsummary: "s"\nhandoff-context:\n  plan-first: maybe\n'

        result = parse_ticket_file(source)

        assert isinstance(result, TicketFileTypeError)
        assert not isinstance(result, TicketFile)
