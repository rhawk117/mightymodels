"""The repository rows: the scope every root table hangs from."""

from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class RepositoryKeyParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_key: str


class RepositoryRow(Struct, frozen=True, kw_only=True, gc=False):
    id: int
    repository_key: str


ENSURE_REPOSITORY = Query(name='ensure_repository', params=RepositoryKeyParams, row=RepositoryRow)
REPOSITORY_BY_KEY = Query(name='repository_by_key', params=RepositoryKeyParams, row=RepositoryRow)

DECLARATIONS: tuple[Declaration, ...] = (ENSURE_REPOSITORY, REPOSITORY_BY_KEY)
