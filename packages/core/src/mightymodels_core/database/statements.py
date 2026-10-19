"""Typed statement declarations: a name, the parameter Struct and, for a query, the row Struct."""

from dataclasses import dataclass
from typing import Any

from msgspec import Struct


@dataclass(slots=True, kw_only=True, frozen=True)
class Query[P: Struct, R: Struct]:
    name: str
    params: type[P]
    row: type[R]


@dataclass(slots=True, kw_only=True, frozen=True)
class Command[P: Struct]:
    name: str
    params: type[P]


type Declaration = Query[Any, Any] | Command[Any]
