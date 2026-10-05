"""Request and result schemas for search_python_docs."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, StringConstraints

from python_harness.documentation.domain import VERSION_PATTERN
from python_harness.documentation.matching import MatchTier

DEFAULT_SEARCH_LIMIT = 10

type VersionText = Annotated[
    str,
    StringConstraints(strict=True, pattern=f'^{VERSION_PATTERN}$'),
    Field(
        description=(
            'Python minor version such as 3.13.\n\n'
            'Read requires-python in pyproject.toml or .python-version first; do not guess.'
        )
    ),
]
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
type SourceUrl = Annotated[str, Field(description='An official, versioned docs.python.org URL.')]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class SearchRequest(Model):
    version: VersionText
    query: SymbolQuery
    limit: SearchLimit


class SearchMatch(Model):
    name: str
    kind: str
    source_url: SourceUrl
    match: MatchTier


class SearchResult(Model):
    python_version: VersionText
    documentation_version: str
    query: str
    total_matches: NonNegativeInt
    matches: list[SearchMatch]
