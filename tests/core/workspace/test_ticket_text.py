from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.workspace import TicketFile, parse_ticket_file
from mightymodels_core.workspace.ticket_text import with_context

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


class TestWithContext:
    @context_rewrite_cases()
    def test_only_the_context_block_is_rewritten(self, rewrite: ContextRewrite) -> None:
        assert with_context(rewrite.source, rewrite.context) == rewrite.expected

    @context_quoting_cases()
    def test_a_line_reads_back_as_written(self, line: str) -> None:
        text = with_context(f'{HEAD}context:\n  - "old"\n', (line,))

        parsed = parse_ticket_file(text)

        assert isinstance(parsed, TicketFile)
        assert parsed.context == (line,)
