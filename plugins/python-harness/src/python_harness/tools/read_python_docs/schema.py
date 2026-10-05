"""Request schema and rendered page for read_python_docs."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field, NonNegativeInt, StringConstraints

from python_harness.documentation.domain import Symbol
from python_harness.tools.search_python_docs.schema import Model, VersionText

DEFAULT_PAGE_CHARACTERS = 8_000

type SymbolName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    Field(description='Exact symbol name from search_python_docs, such as os.path.join.'),
]
type PageOffset = Annotated[
    NonNegativeInt,
    Field(description='Character offset to continue from, as given by a page footer.'),
]
type PageCharacters = Annotated[
    int,
    Field(ge=500, le=12_000, description='Maximum documentation characters to return.'),
]


class ReadRequest(Model):
    version: VersionText
    symbol: SymbolName
    offset: PageOffset
    max_chars: PageCharacters


@dataclass(frozen=True, slots=True, kw_only=True)
class SectionPage:
    symbol: Symbol
    documentation_version: str
    text: str
    offset: int
    max_chars: int

    @property
    def end(self) -> int:
        return min(self.offset + self.max_chars, len(self.text))

    @property
    def header(self) -> str:
        symbol = self.symbol
        return (
            f'{symbol.name} ({symbol.kind}) | Python {self.documentation_version}'
            f' documentation | {symbol.source_url.text}'
        )

    @property
    def footer(self) -> str:
        total = len(self.text)
        if self.end < total:
            return (
                f'More: call read_python_docs again with offset={self.end}'
                f' ({self.end} of {total} characters shown).'
            )
        return f'End of section ({total} characters).'

    def render(self) -> str:
        return '\n\n'.join((self.header, self.text[self.offset : self.end], self.footer))
