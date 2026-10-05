"""Code citations found in Markdown documents and the problems found checking them."""

from dataclasses import dataclass
from enum import StrEnum, auto


@dataclass(frozen=True, slots=True)
class Citation:
    document_line: int
    path: str
    start: int
    end: int
    quote: str | None


class CitationProblem(StrEnum):
    OUTSIDE_WORKSPACE = auto()
    MISSING_FILE = auto()
    UNREADABLE_FILE = auto()
    LINE_OUT_OF_RANGE = auto()
    MISSING_QUOTE = auto()
    QUOTE_NOT_FOUND = auto()


@dataclass(frozen=True, slots=True)
class CitationOptions:
    minimum_quote_characters: int = 3


@dataclass(frozen=True, slots=True)
class CitationFailure:
    citation: Citation
    problem: CitationProblem


@dataclass(frozen=True, slots=True)
class CitationReport:
    document: str
    checked: int
    failures: tuple[CitationFailure, ...]
    uncited_rows: tuple[int, ...]

    @property
    def passed(self) -> bool:
        return not self.failures and not self.uncited_rows
