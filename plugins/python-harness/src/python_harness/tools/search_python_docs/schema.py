"""Request and result schemas for search_python_docs."""

from typing import Annotated

from pydantic import Field, NonNegativeInt, PositiveInt, StringConstraints

from python_harness.documentation.domain import Model, PythonVersion
from python_harness.documentation.matching import SymbolMatch

DEFAULT_SEARCH_LIMIT = 10

type SymbolQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    Field(
        description=(
            'Symbol name or dotted-name fragments, such as json.loads or ordered dict;'
            ' not a question.'
        )
    ),
]
type SearchLimit = Annotated[
    PositiveInt, Field(le=30, description='Maximum number of matches to return.')
]


class SearchRequest(Model):
    version: PythonVersion
    query: SymbolQuery
    limit: SearchLimit


class SearchResult(Model):
    python_version: PythonVersion
    documentation_version: str
    query: str
    total_matches: NonNegativeInt
    matches: list[SymbolMatch]
