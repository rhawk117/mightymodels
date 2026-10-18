"""The similarity rows of a repository and the full-text search over them."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Command, Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class SimilarityKind(StrEnum):
    LEDGER_ENTRY = 'ledger-entry'
    SCOUT_REPORT = 'scout-report'
    REVIEW_FINDING = 'review-finding'
    CRASHOUT = 'crashout'


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
    """`query` is an FTS5 MATCH expression; a null `kind` matches every kind, and a null
    `excluded_reference` excludes nothing, otherwise the (`excluded_kind`, `excluded_reference`)
    pair is left out."""

    repository_id: int
    query: str
    kind: SimilarityKind | None
    excluded_kind: SimilarityKind | None
    excluded_reference: str | None


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
