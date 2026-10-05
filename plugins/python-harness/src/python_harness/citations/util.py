"""Citations, their quotes and uncited table rows in Markdown, outside fenced blocks."""

import re
from collections.abc import Iterator
from itertools import chain, pairwise

from python_harness.citations.domain import Citation

CITATION = re.compile(
    r"""
    (?<![\w./-])
    (?P<tick>`)?
    (?P<path>[\w./-]++(?<=\.py))
    :(?P<start>\d++)
    (?:-(?P<end>\d++))?
    (?(tick)`)
    """,
    re.VERBOSE,
)
QUOTE = re.compile(r'`(?P<quote>[^`]++)`')
FENCE_OPENING = re.compile(r'[ \t]*+(?P<marker>`{3,}+|~{3,}+)')
SEPARATOR_CHARACTERS = frozenset('|:- \t')

type NumberedLine = tuple[int, str]

END_OF_DOCUMENT: NumberedLine = (0, '')


def find_opening_fence(line: str) -> str | None:
    found = FENCE_OPENING.match(line)
    return None if found is None else str(found['marker'])


def closes_fence(line: str, marker: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(marker) and not stripped.strip(marker[0])


def find_open_fence_after(open_marker: str | None, line: str) -> str | None:
    if open_marker is None:
        return find_opening_fence(line)
    if closes_fence(line, open_marker):
        return None
    return open_marker


def number_unfenced_lines(text: str) -> Iterator[NumberedLine]:
    open_marker: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        open_before = open_marker
        open_marker = find_open_fence_after(open_marker, line)
        if open_before is None and open_marker is None:
            yield number, line


def unescape_table_pipes(text: str) -> str:
    return text.replace('\\|', '|')


def find_quote(line: str, start: int, end: int) -> str | None:
    found = QUOTE.search(line, start, end)
    return None if found is None else unescape_table_pipes(found['quote'])


def citation_from_match(document_line: int, match: re.Match[str], quote: str | None) -> Citation:
    start = int(match['start'])
    end = start if match['end'] is None else int(match['end'])
    return Citation(document_line, match['path'], start, end, quote)


def citations_on_line(document_line: int, line: str) -> Iterator[Citation]:
    matches = tuple(CITATION.finditer(line))
    boundaries = (*(match.start() for match in matches), len(line))
    for match, quote_end in zip(matches, boundaries[1:], strict=True):
        quote = find_quote(line, match.end(), quote_end)
        yield citation_from_match(document_line, match, quote)


def parse_citations(text: str) -> tuple[Citation, ...]:
    lines = number_unfenced_lines(text)
    per_line = (citations_on_line(number, line) for number, line in lines)
    return tuple(chain.from_iterable(per_line))


def is_table_row(line: str) -> bool:
    return line.lstrip().startswith('|')


def is_separator_row(line: str) -> bool:
    stripped = line.strip()
    dashed = '-' in stripped and SEPARATOR_CHARACTERS.issuperset(stripped)
    return dashed and is_table_row(stripped)


def is_data_row(line: str, following: str) -> bool:
    if not is_table_row(line) or is_separator_row(line):
        return False
    return not is_separator_row(following)


def select_data_rows(text: str) -> Iterator[NumberedLine]:
    numbered = pairwise((*number_unfenced_lines(text), END_OF_DOCUMENT))
    for (number, line), (_, following) in numbered:
        if is_data_row(line, following):
            yield number, line


def find_uncited_rows(text: str) -> tuple[int, ...]:
    rows = select_data_rows(text)
    return tuple(number for number, line in rows if CITATION.search(line) is None)
