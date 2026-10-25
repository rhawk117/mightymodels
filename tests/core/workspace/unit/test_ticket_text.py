from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.workspace import (
    CompanionDocsFile,
    HandoffContextFile,
    LoneSurrogateError,
    TicketFile,
    parse_ticket_file,
)
from mightymodels_core.workspace.ticket_text import render_ticket, with_context

from tests.core.workspace.workspace_builders import ESCAPED_CHARACTERS, LONE_SURROGATES

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

HEAD = 'task: "alpha"\nsummary: "s"\n'
TAIL = 'handoff-context:\n  scope: med\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class ContextRewrite:
    name: str
    source: str
    context: tuple[str, ...]
    expected: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def context_rewrite_cases() -> pytest.MarkDecorator:
    scenarios = [
        ContextRewrite(
            name='replaces-the-block-between-other-keys',
            source=f'{HEAD}context:\n  - "old"\n  - "older"\n{TAIL}',
            context=('new',),
            expected=f'{HEAD}context:\n  - "new"\n{TAIL}',
        ),
        ContextRewrite(
            name='replaces-the-last-block',
            source=f'{HEAD}{TAIL}context:\n  - "old"\n',
            context=('a', 'b'),
            expected=f'{HEAD}{TAIL}context:\n  - "a"\n  - "b"\n',
        ),
        ContextRewrite(
            name='appends-when-the-key-is-absent',
            source=f'{HEAD}{TAIL}',
            context=('new',),
            expected=f'{HEAD}{TAIL}context:\n  - "new"\n',
        ),
        ContextRewrite(
            name='keeps-a-comment-below-the-block',
            source=f'{HEAD}context:\n  - "old"\n# note\n{TAIL}',
            context=('new',),
            expected=f'{HEAD}context:\n  - "new"\n# note\n{TAIL}',
        ),
        ContextRewrite(
            name='adds-the-final-newline',
            source=f'{HEAD}context:\n  - "old"',
            context=('new',),
            expected=f'{HEAD}context:\n  - "new"\n',
        ),
    ]
    return pytest.mark.parametrize('rewrite', [scenario.param for scenario in scenarios])


class TestWithContext:
    lines = st.text()
    surrogates = LONE_SURROGATES

    @context_rewrite_cases()
    def test_only_the_context_block_is_rewritten(self, rewrite: ContextRewrite) -> None:
        assert with_context(rewrite.source, rewrite.context) == rewrite.expected

    @given(line=lines)
    @example(line='a: b')
    @example(line='c # d')
    @example(line='say "x"')
    @example(line='back\\slash')
    @example(line='tab\there')
    @example(line='ünï')
    def test_a_line_reads_back_as_written(self, line: str) -> None:
        text = with_context(f'{HEAD}context:\n  - "old"\n', (line,))

        assert isinstance(text, str)
        parsed = parse_ticket_file(text)

        assert isinstance(parsed, TicketFile)
        assert parsed.context == (line,)

    @given(surrogate=surrogates)
    @example(surrogate='\ud800')
    @example(surrogate='\udbff')
    @example(surrogate='\udc00')
    @example(surrogate='\udfff')
    def test_a_lone_surrogate_is_returned_as_the_refusal(self, surrogate: str) -> None:
        refusal = with_context(f'{HEAD}context:\n  - "old"\n', (f'a{surrogate}b',))

        assert isinstance(refusal, LoneSurrogateError)
        assert refusal.character == surrogate


class TestRenderTicket:
    ticket = TicketFile(
        task='alpha',
        summary='s',
        triaged_at='2026-01-02T03:04:05+00:00',
        context=('a', 'b'),
        companion_docs=CompanionDocsFile(
            issue_number=7, jira_key=None, reference_urls=('https://example.com',)
        ),
        subagent_models={'primary-agent': None, 'engineer': 'sonnet'},
        handoff_context=HandoffContextFile(
            scope='med', plan_first=True, branch_name='feat/x', worktrees_okay=False
        ),
        investigations=('first-look',),
    )
    escaped_characters = ESCAPED_CHARACTERS
    surrogates = LONE_SURROGATES

    def test_keys_come_in_the_fixed_order(self) -> None:
        assert render_ticket(self.ticket) == (
            'task: "alpha"\n'
            'summary: "s"\n'
            'triaged-at: "2026-01-02T03:04:05+00:00"\n'
            'context:\n  - "a"\n  - "b"\n'
            'companion-docs:\n  issue-number: 7\n  jira-key:\n'
            '  reference-urls:\n    - "https://example.com"\n'
            'subagent-models:\n  primary-agent:\n  engineer: "sonnet"\n'
            'handoff-context:\n  scope: "med"\n  plan-first: true\n'
            '  branch-name: "feat/x"\n  worktrees-okay: false\n'
            'investigations:\n  - "first-look"\n'
        )

    def test_the_rendered_text_reads_back(self) -> None:
        rendered = render_ticket(self.ticket)

        assert isinstance(rendered, str)
        assert parse_ticket_file(rendered) == self.ticket

    @given(character=escaped_characters)
    @example(character='\x85')
    @example(character='\u2028')
    @example(character='\u2029')
    @example(character='\x7f')
    @example(character='\x9f')
    @example(character='\x00')
    @example(character='\ufffe')
    @example(character='\uffff')
    def test_a_refused_character_is_escaped_and_reads_back(self, character: str) -> None:
        text = f'a{character}b'
        rendered = render_ticket(
            TicketFile(task=self.ticket.task, summary=text, context=self.ticket.context)
        )

        assert isinstance(rendered, str)
        parsed = parse_ticket_file(rendered)

        assert character not in rendered
        assert isinstance(parsed, TicketFile)
        assert parsed.summary == text

    @given(surrogate=surrogates)
    @example(surrogate='\ud800')
    @example(surrogate='\udbff')
    @example(surrogate='\udc00')
    @example(surrogate='\udfff')
    def test_a_lone_surrogate_is_returned_as_the_refusal(self, surrogate: str) -> None:
        refusal = render_ticket(TicketFile(task=self.ticket.task, summary=f'a{surrogate}b'))

        assert isinstance(refusal, LoneSurrogateError)
        assert refusal.character == surrogate
        assert f'U+{ord(surrogate):04X}' in str(refusal)

    def test_a_lone_surrogate_in_a_list_value_is_returned_as_the_refusal(self) -> None:
        refusal = render_ticket(TicketFile(task=self.ticket.task, context=('ok', '\ud800')))

        assert isinstance(refusal, LoneSurrogateError)
