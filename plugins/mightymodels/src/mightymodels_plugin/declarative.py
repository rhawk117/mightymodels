"""What every table of the state database is declared from.

A domain declares its rows in its own `tables.py` from this base and these column types, and
`database.py` names every row type it creates a table for.

Every row type has a `repository_key` column, because one database holds the rows of every
repository. It leads the primary key of a table keyed by names, so the same slug, task id, run id
or investigation id is a different row in another repository. A table keyed by a serial number
carries it as a plain column, and the number orders the rows of one repository.
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
