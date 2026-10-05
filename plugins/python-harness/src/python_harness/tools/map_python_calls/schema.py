"""Request schema for map_python_calls."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field, StringConstraints

type SymbolReference = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
    Field(
        description=(
            'One symbol to list every reference of, as a bare name or module.name;'
            ' leave out for the per-module summary.'
        )
    ),
]


@dataclass(frozen=True, slots=True, kw_only=True)
class CallsRequest:
    paths: tuple[str, ...]
    symbol: str | None
