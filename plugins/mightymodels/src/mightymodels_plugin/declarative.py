"""What every table of `.mightymodels/mightymodels.db` is declared from.

A domain declares its rows in its own `tables.py` from this base and these column types, and
`database.py` names every row type it creates a table for.
"""

from types import MappingProxyType
from typing import Annotated

from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, mapped_column

type Models = dict[str, str | None]
type Weights = dict[str, float]
type Texts = list[str]
type Key = Annotated[str, mapped_column(primary_key=True)]
type Serial = Annotated[int, mapped_column(primary_key=True)]
type Indexed = Annotated[str, mapped_column(index=True)]


class Base(DeclarativeBase):
    type_annotation_map = MappingProxyType({Models: JSON, Texts: JSON, Weights: JSON})
