"""Request schema for check_citations."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field, StringConstraints

INLINE_DOCUMENT_NAME = '<text>'

DocumentPath = Annotated[
    str,
    StringConstraints(pattern=r'^[^\x00]*$'),
    Field(
        description=(
            'A Markdown file inside the project, relative to its root. Empty means not given.'
        )
    ),
]
DocumentText = Annotated[
    str,
    Field(
        description=(
            'The Markdown to check, verbatim, when it is not a file in the project.'
            ' Empty means not given.'
        )
    ),
]


@dataclass(frozen=True, slots=True, kw_only=True)
class CitationsRequest:
    path: str | None
    text: str | None
