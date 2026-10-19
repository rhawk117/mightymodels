"""ticket.yml text made as text: a new ticket rendered from its values, or one block rewritten.

A rewrite leaves the lines outside the block as written, and a comment or a blank line that
follows a block stays below the block's new lines.
"""

import re
from typing import TYPE_CHECKING

from mightymodels_core.primitives import INDENT, encode_compact

from .ticket_file import CompanionDocsFile, HandoffContextFile
from .ticket_scan import LIST_MARK, SourceLine, source_line, split_lines

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .ticket_file import TicketFile

type Scalar = str | int | bool | None

CONTEXT_KEY = 'context'
RAW_LINE_BREAKS = re.compile('[\x7f-\x9f\u2028\u2029]')


def escape_raw_break(match: re.Match[str]) -> str:
    return f'\\u{ord(match[0]):04x}'


def quoted(value: str) -> str:
    return RAW_LINE_BREAKS.sub(escape_raw_break, encode_compact(value).decode())


def scalar_text(value: Scalar) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    return quoted(value)


def entry_line(key: str, value: Scalar, *, depth: int = 0) -> str:
    return f'{" " * (depth * INDENT)}{key}: {scalar_text(value)}'.rstrip()


def list_lines(key: str, values: Sequence[str], *, depth: int = 0) -> list[str]:
    pad = ' ' * (depth * INDENT)
    return [f'{pad}{key}:', *(f'{pad}{" " * INDENT}{LIST_MARK}{quoted(value)}' for value in values)]


def key_of(line: SourceLine) -> str:
    return line.text.partition(':')[0]


def block_end(lines: Sequence[SourceLine], key: str, line_count: int) -> tuple[int, int]:
    """Return the line the key's block starts on and the last line it holds."""
    after_file = line_count + 1
    top_level = [line for line in lines if not line.indent]
    start = next((line.number for line in top_level if key_of(line) == key), after_file)
    following = next((line.number for line in top_level if line.number > start), after_file)
    last = max((line.number for line in lines if start < line.number < following), default=start)
    return start, last


def with_context(source: str, context: Sequence[str]) -> str:
    raw = split_lines(source)
    numbered = (source_line(number, text) for number, text in enumerate(raw, 1))
    lines = [line for line in numbered if isinstance(line, SourceLine)]
    start, last = block_end(lines, CONTEXT_KEY, len(raw))
    updated = [*raw[: start - 1], *list_lines(CONTEXT_KEY, context), *raw[last:]]
    return '\n'.join(updated) + '\n'


def render_ticket(ticket: TicketFile) -> str:
    handoff = ticket.handoff_context or HandoffContextFile()
    companions = ticket.companion_docs or CompanionDocsFile()
    models = ticket.subagent_models or {}
    lines = [
        entry_line('task', ticket.task),
        entry_line('summary', ticket.summary),
        entry_line('triaged-at', ticket.triaged_at),
        *list_lines(CONTEXT_KEY, ticket.context or ()),
        'companion-docs:',
        entry_line('issue-number', companions.issue_number, depth=1),
        entry_line('jira-key', companions.jira_key, depth=1),
        *list_lines('reference-urls', companions.reference_urls or (), depth=1),
        'subagent-models:',
        *(entry_line(worker, model, depth=1) for worker, model in models.items()),
        'handoff-context:',
        entry_line('scope', handoff.scope, depth=1),
        entry_line('plan-first', handoff.plan_first, depth=1),
        entry_line('branch-name', handoff.branch_name, depth=1),
        entry_line('worktrees-okay', handoff.worktrees_okay, depth=1),
        *list_lines('investigations', ticket.investigations or ()),
    ]
    return '\n'.join(lines) + '\n'
