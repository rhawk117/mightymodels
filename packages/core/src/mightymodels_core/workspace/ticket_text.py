"""ticket.yml text rewritten as text: the lines outside the rewritten block stay as written.

A comment or a blank line that follows a block stays below the block's new lines.
"""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import encode_compact

from .ticket_scan import LIST_MARK, SourceLine, source_line, split_lines

if TYPE_CHECKING:
    from collections.abc import Sequence

CONTEXT_KEY = 'context'


def quoted(value: str) -> str:
    return encode_compact(value).decode()


def list_lines(key: str, values: Sequence[str]) -> list[str]:
    return [f'{key}:', *(f'{" " * 2}{LIST_MARK}{quoted(value)}' for value in values)]


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
