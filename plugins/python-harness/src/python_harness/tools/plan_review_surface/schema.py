"""Request schema for plan_review_surface."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field, StringConstraints

type Revision = Annotated[
    str,
    StringConstraints(pattern=r'^[^-\x00][^\x00]*$'),
    Field(description='A git revision such as origin/main or HEAD; it cannot start with a dash.'),
]


@dataclass(frozen=True, slots=True, kw_only=True)
class SurfaceRequest:
    paths: tuple[str, ...] | None
    diff_base: str | None
    diff_head: str | None
