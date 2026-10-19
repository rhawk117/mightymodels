"""The similarity rows of a repository and the full-text search over them.

In `SimilarityCandidatesParams`, `query` is an FTS5 MATCH expression and `limit` caps the rows
returned. A null `kind` matches every kind, and a null `excluded_reference` excludes nothing,
otherwise the (`excluded_kind`, `excluded_reference`) pair is left out.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from msgspec import Struct

from mightymodels_core.database import Command, Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


type SimilarityKind = Literal['ledger-entry', 'scout-report', 'review-finding', 'crashout']
type FtsMatchExpression = str


class UpsertSimilarityParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    kind: SimilarityKind
    reference: str
    text: str


class SimilarityReferenceParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    kind: SimilarityKind
    reference: str


class SimilarityCandidatesParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    query: FtsMatchExpression
    kind: SimilarityKind | None
    excluded_kind: SimilarityKind | None
    excluded_reference: str | None
    limit: int


class SimilarityRow(Struct, frozen=True, kw_only=True, gc=False):
    id: int
    kind: SimilarityKind
    reference: str
    text: str
    at: datetime


class SimilarityCandidateRow(Struct, frozen=True, kw_only=True, gc=False):
    kind: SimilarityKind
    reference: str
    text: str


UPSERT_SIMILARITY = Command(name='upsert_similarity', params=UpsertSimilarityParams)
SIMILARITY_OF_REFERENCE = Query(
    name='similarity_of_reference', params=SimilarityReferenceParams, row=SimilarityRow
)
SIMILARITY_CANDIDATES = Query(
    name='similarity_candidates', params=SimilarityCandidatesParams, row=SimilarityCandidateRow
)

DECLARATIONS: tuple[Declaration, ...] = (
    UPSERT_SIMILARITY,
    SIMILARITY_OF_REFERENCE,
    SIMILARITY_CANDIDATES,
)
