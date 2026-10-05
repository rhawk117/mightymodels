"""Request schema for check_citations."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from python_harness.tools.project import ProjectPath

INLINE_DOCUMENT_NAME = '<text>'

type DocumentPath = Annotated[
    ProjectPath,
    Field(description='A Markdown file inside the project, relative to its root.'),
]
type DocumentText = Annotated[
    str,
    Field(description='The Markdown to check, verbatim, when it is not a file in the project.'),
]


@dataclass(frozen=True, slots=True, kw_only=True)
class CitationsRequest:
    path: str | None
    text: str | None
