"""The similarity and scout report repositories kept in memory."""

from dataclasses import dataclass, field
from operator import attrgetter
from typing import TYPE_CHECKING

from mightymodels_core.similarity.matching import (
    CANDIDATE_CAP,
    content_words,
    duplicate_of,
    matches_of,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mightymodels_core.schemas.similarity import SimilarityKind
    from mightymodels_core.similarity.records import Duplicate, Match, ScoutReport, Written

type EntryKey = tuple[SimilarityKind, str]


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityLedger:
    entries: dict[EntryKey, Written] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeSimilarityRepository:
    ledger: SimilarityLedger = field(default_factory=SimilarityLedger)

    def candidates(
        self,
        words: frozenset[str],
        *,
        kind: SimilarityKind | None,
        excluding: Written | None,
    ) -> list[Written]:
        held = [
            entry
            for key, entry in self.ledger.entries.items()
            if (kind is None or entry.kind == kind)
            and (excluding is None or key != (excluding.kind, excluding.reference))
            and words & content_words(entry.text)
        ]
        closest_first = sorted(matches_of(held, words), key=attrgetter('overlap'), reverse=True)
        kept = {(match.kind, match.reference) for match in closest_first[:CANDIDATE_CAP]}
        return [entry for entry in held if (entry.kind, entry.reference) in kept]

    def search(self, query: str, *, kind: SimilarityKind | None) -> list[Match]:
        words = content_words(query)
        return matches_of(self.candidates(words, kind=kind, excluding=None), words)

    def entry(self, kind: SimilarityKind, reference: str) -> Written | None:
        return self.ledger.entries.get((kind, reference))

    def record(self, written: Written) -> Duplicate | None:
        words = content_words(written.text)
        candidates = self.candidates(words, kind=None, excluding=written)
        duplicate = duplicate_of(written, candidates)
        self.ledger.entries[(written.kind, written.reference)] = written
        return duplicate

    def record_all(self, writes: Iterable[Written]) -> list[Duplicate]:
        duplicates = [self.record(written) for written in writes]
        return [duplicate for duplicate in duplicates if duplicate is not None]


@dataclass(slots=True, kw_only=True, frozen=True)
class ScoutReportLedger:
    reports: list[ScoutReport] = field(default_factory=list)


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeScoutReportRepository:
    ledger: ScoutReportLedger = field(default_factory=ScoutReportLedger)

    def has_report(self, report: ScoutReport) -> bool:
        return any(
            held.scout == report.scout and held.target == report.target
            for held in self.ledger.reports
        )

    def add_report(self, report: ScoutReport) -> int:
        self.ledger.reports.append(report)
        return len(self.ledger.reports)
