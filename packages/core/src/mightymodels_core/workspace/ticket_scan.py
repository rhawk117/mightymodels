"""The pre-scan of ticket.yml: the YAML subset a hand edit may use, refused with its line.

The subset is two levels of mappings, scalars and lists of scalars, with trailing comments, every
line indented with spaces in steps of two. PyYAML accepts more than that and keeps the last of a
duplicate key, so the scan refuses what it would read differently from the file's author. A line
ends at a newline, a carriage return or the pair and nowhere else; PyYAML also breaks a line at
U+0085, U+2028 and U+2029 and refuses control characters without naming a line, so the scan
refuses all of those with the line they sit on. The scan also records the line of every key path,
so a type refusal that only names a path can point at its line.
"""

import io
import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import TicketFileSyntaxError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

INDENT = 2
LIST_MARK = '- '
ROOT_PATH = '$'
UNREADABLE = re.compile(
    '[^\t\n\r\x20-\x7e\xa0-\u2027\u202a-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]'
)
KEY_QUOTES = ('"', "'")
CLOSED_DOUBLE_QUOTE = re.compile(r'"(?:[^"\\]|\\.)*"')
UNSUPPORTED_STARTS = ("'", '[', '{', '&', '*', '!', '|', '>')


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceLine:
    number: int
    indent: int
    text: str


@dataclass(slots=True, kw_only=True, frozen=True)
class KeyLine:
    number: int
    path: str


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketScan:
    key_lines: Mapping[str, int]

    @property
    def is_empty(self) -> bool:
        return not self.key_lines

    def line_of(self, key_path: str) -> int | None:
        return self.key_lines.get(key_path)


def split_lines(source: str) -> list[str]:
    return [line.removesuffix('\n') for line in io.StringIO(source, newline=None)]


def get_unreadable_problem(number: int, raw: str) -> TicketFileSyntaxError | None:
    unreadable = UNREADABLE.search(raw)
    if not unreadable:
        return None

    return TicketFileSyntaxError(
        line=number,
        reason=f'the line holds U+{ord(unreadable[0]):04X}, which a ticket file cannot hold',
    )


def is_skipped_line(raw: str) -> bool:
    stripped = raw.lstrip()
    return not stripped.strip() or stripped.startswith('#')


def indentation_problem(number: int, leading: str) -> TicketFileSyntaxError | None:
    if '\t' in leading:
        return TicketFileSyntaxError(
            line=number, reason='the indentation holds a tab; indent with two spaces per level'
        )

    if (character := next((char for char in leading if char != ' '), None)) is not None:
        return TicketFileSyntaxError(
            line=number,
            reason=(
                f'the indentation holds U+{ord(character):04X}, which is not a space; '
                'indent with two spaces per level'
            ),
        )

    return None


def source_line(number: int, raw: str) -> SourceLine | TicketFileSyntaxError | None:
    stripped = raw.lstrip()
    if is_skipped_line(raw):
        return get_unreadable_problem(number, raw)

    leading = raw.removesuffix(stripped)
    if problem := indentation_problem(number, leading):
        return problem

    if problem := get_unreadable_problem(number, raw):
        return problem

    content = raw.rstrip()
    indent = len(content) - len(content.lstrip(' '))
    if indent % INDENT:
        return TicketFileSyntaxError(
            line=number, reason='indentation must be a multiple of two spaces'
        )

    return SourceLine(number=number, indent=indent, text=content.strip())


def value_of(text: str) -> str:
    if text.startswith(LIST_MARK):
        return text.removeprefix(LIST_MARK).strip()
    return text.partition(':')[2].strip()


def is_unclosed_double_quote(value: str) -> bool:
    return value.startswith('"') and not CLOSED_DOUBLE_QUOTE.match(value)


def has_unsupported_key(text: str) -> bool:
    key = text.partition(':')[0]
    return key.startswith(KEY_QUOTES) or any(char.isspace() for char in key)


def get_key_problem(line: SourceLine) -> TicketFileSyntaxError | None:
    if ':' not in line.text:
        return TicketFileSyntaxError(
            line=line.number, reason=f'expected "key: value", got {line.text}'
        )

    if has_unsupported_key(line.text):
        return TicketFileSyntaxError(
            line=line.number,
            reason=f'a key holds no whitespace and no quote, got {line.text}',
        )

    return None


def get_line_problem(line: SourceLine) -> TicketFileSyntaxError | None:
    is_item = line.text.startswith(LIST_MARK)
    if is_item and not line.indent:
        return TicketFileSyntaxError(
            line=line.number, reason='a list item is indented under its key'
        )

    if not is_item and (problem := get_key_problem(line)):
        return problem

    value = value_of(line.text)
    if value.startswith(UNSUPPORTED_STARTS) or is_unclosed_double_quote(value):
        return TicketFileSyntaxError(line=line.number, reason=f'unsupported YAML syntax: {value}')

    return None


def get_scanned_problem(
    item: SourceLine | TicketFileSyntaxError | None,
) -> TicketFileSyntaxError | None:
    if isinstance(item, SourceLine):
        return get_line_problem(item)
    return item


def key_lines(lines: Iterable[SourceLine]) -> list[KeyLine]:
    parents: list[tuple[int, str]] = []
    item_counts: Counter[str] = Counter()
    keyed: list[KeyLine] = []
    for line in lines:
        while parents and parents[-1][0] >= line.indent:
            parents.pop()

        parent = parents[-1][1] if parents else ROOT_PATH
        if line.text.startswith(LIST_MARK):
            path = f'{parent}[{item_counts[parent]}]'
            item_counts[parent] += 1
        else:
            path = f'{parent}.{line.text.partition(":")[0]}'
            parents.append((line.indent, path))

        keyed.append(KeyLine(number=line.number, path=path))
    return keyed


def get_duplicate_problem(keyed: list[KeyLine]) -> TicketFileSyntaxError | None:
    first_lines: dict[str, int] = {}
    for entry in keyed:
        first_lines.setdefault(entry.path, entry.number)

    duplicate = next((entry for entry in keyed if first_lines[entry.path] != entry.number), None)
    if duplicate is None:
        return None

    key = duplicate.path.rpartition('.')[2]
    return TicketFileSyntaxError(line=duplicate.number, reason=f'duplicate key {key}')


def scan_ticket(source: str) -> TicketScan | TicketFileSyntaxError:
    scanned = [source_line(number, raw) for number, raw in enumerate(split_lines(source), 1)]
    if problem := next(filter(None, map(get_scanned_problem, scanned)), None):
        return problem

    keyed = key_lines(item for item in scanned if isinstance(item, SourceLine))
    if problem := get_duplicate_problem(keyed):
        return problem

    return TicketScan(key_lines={entry.path: entry.number for entry in keyed})
