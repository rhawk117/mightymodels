from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.workspace import (
    CompanionDocsFile,
    HandoffContextFile,
    LoneSurrogateError,
    TicketFile,
    parse_ticket_file,
)
from mightymodels_core.workspace.ticket_text import render_ticket, with_context

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


def context_quoting_cases() -> pytest.MarkDecorator:
    lines = ['a: b', 'c # d', 'say "x"', 'back\\slash', 'tab\there', 'ünï']
    return pytest.mark.parametrize('line', [pytest.param(line, id=line[:6]) for line in lines])


def lone_surrogate_cases() -> pytest.MarkDecorator:
    surrogates = ['\ud800', '\udbff', '\udc00', '\udfff']
    return pytest.mark.parametrize(
        'surrogate', [pytest.param(char, id=ascii(char)) for char in surrogates]
    )


def noncharacter_cases() -> pytest.MarkDecorator:
    noncharacters = {'u-fffe': '\ufffe', 'u-ffff': '\uffff'}
    return pytest.mark.parametrize(
        'noncharacter', [pytest.param(char, id=name) for name, char in noncharacters.items()]
    )


class TestWithContext:
    @context_rewrite_cases()
    def test_only_the_context_block_is_rewritten(self, rewrite: ContextRewrite) -> None:
        assert with_context(rewrite.source, rewrite.context) == rewrite.expected

    @context_quoting_cases()
    def test_a_line_reads_back_as_written(self, line: str) -> None:
        text = with_context(f'{HEAD}context:\n  - "old"\n', (line,))

        assert isinstance(text, str)
        parsed = parse_ticket_file(text)

        assert isinstance(parsed, TicketFile)
        assert parsed.context == (line,)

    @lone_surrogate_cases()
    def test_a_lone_surrogate_is_returned_as_the_refusal(self, surrogate: str) -> None:
        refusal = with_context(f'{HEAD}context:\n  - "old"\n', (f'a{surrogate}b',))

        assert isinstance(refusal, LoneSurrogateError)
        assert refusal.character == surrogate


def ticket_escape_cases() -> pytest.MarkDecorator:
    texts = ['next\u0085', 'sep\u2028', 'para\u2029', 'del\x7f', 'c1\x9f', 'nul\x00']
    return pytest.mark.parametrize('text', [pytest.param(text, id=ascii(text)) for text in texts])


class TestRenderTicket:
    @pytest.fixture
    def ticket(self) -> TicketFile:
        return TicketFile(
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

    def test_keys_come_in_the_fixed_order(self, ticket: TicketFile) -> None:
        assert render_ticket(ticket) == (
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

    def test_the_rendered_text_reads_back(self, ticket: TicketFile) -> None:
        rendered = render_ticket(ticket)

        assert isinstance(rendered, str)
        assert parse_ticket_file(rendered) == ticket

    @ticket_escape_cases()
    def test_a_refused_character_is_escaped_and_reads_back(
        self, ticket: TicketFile, text: str
    ) -> None:
        rendered = render_ticket(TicketFile(task=ticket.task, summary=text, context=ticket.context))

        assert isinstance(rendered, str)
        parsed = parse_ticket_file(rendered)

        assert text not in rendered
        assert isinstance(parsed, TicketFile)
        assert parsed.summary == text

    @noncharacter_cases()
    def test_a_noncharacter_is_escaped_and_reads_back(
        self, ticket: TicketFile, noncharacter: str
    ) -> None:
        text = f'a{noncharacter}b'
        rendered = render_ticket(TicketFile(task=ticket.task, summary=text, context=ticket.context))

        assert isinstance(rendered, str)
        parsed = parse_ticket_file(rendered)
        assert noncharacter not in rendered
        assert isinstance(parsed, TicketFile)
        assert parsed.summary == text

    @lone_surrogate_cases()
    def test_a_lone_surrogate_is_returned_as_the_refusal(
        self, ticket: TicketFile, surrogate: str
    ) -> None:
        refusal = render_ticket(TicketFile(task=ticket.task, summary=f'a{surrogate}b'))

        assert isinstance(refusal, LoneSurrogateError)
        assert refusal.character == surrogate
        assert f'U+{ord(surrogate):04X}' in str(refusal)

    def test_a_lone_surrogate_in_a_list_value_is_returned_as_the_refusal(
        self, ticket: TicketFile
    ) -> None:
        refusal = render_ticket(TicketFile(task=ticket.task, context=('ok', '\ud800')))

        assert isinstance(refusal, LoneSurrogateError)
