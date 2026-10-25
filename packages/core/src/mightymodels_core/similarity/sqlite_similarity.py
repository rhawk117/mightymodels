"""The similarity repository over a core unit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact
from mightymodels_core.schemas.similarity import (
    SIMILARITY_CANDIDATES,
    SIMILARITY_OF_REFERENCE,
    UPSERT_SIMILARITY,
    SimilarityCandidatesParams,
    SimilarityReferenceParams,
    UpsertSimilarityParams,
)
from mightymodels_core.similarity.matching import (
    CANDIDATE_CAP,
    content_words,
    duplicate_of,
    index_query,
    matches_of,
)
from mightymodels_core.similarity.records import Written

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mightymodels_core.database import Unit
    from mightymodels_core.schemas.similarity import (
        SimilarityCandidateRow,
        SimilarityKind,
        SimilarityRow,
    )
    from mightymodels_core.similarity.records import Duplicate, Match


type SimilarityEntryRow = SimilarityCandidateRow | SimilarityRow


def written_of(row: SimilarityEntryRow) -> Written:
    return Written(kind=row.kind, reference=row.reference, text=redact(row.text))


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteSimilarityRepository:
    unit: Unit
    repository_id: int

    def candidates(
        self,
        words: frozenset[str],
        *,
        kind: SimilarityKind | None,
        excluding: Written | None,
    ) -> list[Written]:
        if not words:
            return []

        params = SimilarityCandidatesParams(
            repository_id=self.repository_id,
            query=index_query(words),
            kind=kind,
            excluded_kind=None if excluding is None else excluding.kind,
            excluded_reference=None if excluding is None else excluding.reference,
            limit=CANDIDATE_CAP,
        )
        return [written_of(row) for row in self.unit.all(SIMILARITY_CANDIDATES, params)]

    def search(self, query: str, *, kind: SimilarityKind | None) -> list[Match]:
        words = content_words(query)
        return matches_of(self.candidates(words, kind=kind, excluding=None), words)

    def entry(self, kind: SimilarityKind, reference: str) -> Written | None:
        params = SimilarityReferenceParams(
            repository_id=self.repository_id, kind=kind, reference=reference
        )
        row = self.unit.one(SIMILARITY_OF_REFERENCE, params)
        return None if row is None else written_of(row)

    def record(self, written: Written) -> Duplicate | None:
        words = content_words(written.text)
        candidates = self.candidates(words, kind=None, excluding=written)
        duplicate = duplicate_of(written, candidates)
        params = UpsertSimilarityParams(
            repository_id=self.repository_id,
            kind=written.kind,
            reference=written.reference,
            text=written.text,
        )
        self.unit.run(UPSERT_SIMILARITY, params)
        return duplicate

    def record_all(self, writes: Iterable[Written]) -> list[Duplicate]:
        duplicates = [self.record(written) for written in writes]
        return [duplicate for duplicate in duplicates if duplicate is not None]
