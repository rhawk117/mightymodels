"""Request schema for collect_python_facts."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

type FunctionShapes = Annotated[
    bool,
    Field(
        description=(
            'Also report one function_shape fact per function (parameters, statements,'
            ' nesting depth). Most of the output when on, so ask for it per module.'
        )
    ),
]


@dataclass(frozen=True, slots=True, kw_only=True)
class FactsRequest:
    paths: tuple[str, ...]
    with_function_shapes: bool
