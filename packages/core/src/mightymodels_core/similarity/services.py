"""The similarity service: search, store a scout report, and ask whether one is already stored.

It takes values and returns values. The caller wraps a call in its unit of work and words the
response; the scout report spool is gone, so a report goes straight to the repository. A report's
target and body are redacted within their limits before anything is written, and one that
redaction lengthens past its limit refuses the report. A stored report is sent to the similarity
repository under its row id.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact, redact_within
from mightymodels_core.similarity.records import ScoutReport, Written

if TYPE_CHECKING:
    from mightymodels_core.schemas.scout_reports import Scout
    from mightymodels_core.schemas.similarity import SimilarityKind
    from mightymodels_core.similarity.records import Duplicate, Match
    from mightymodels_core.similarity.repository import (
        ScoutReportRepository,
        SimilarityRepository,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityOptions:
    name_limit: int = 255
    report_limit: int = 60000


@dataclass(slots=True, kw_only=True, frozen=True)
class IncomingReport:
    scout: Scout
    target: str
    report: str


@dataclass(slots=True, kw_only=True, frozen=True)
class StoredReport:
    id: int
    duplicates: tuple[Duplicate, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityService:
    similarity: SimilarityRepository
    scouts: ScoutReportRepository
    options: SimilarityOptions = field(default_factory=SimilarityOptions)

    def search(self, query: str, kind: SimilarityKind | None) -> list[Match]:
        return self.similarity.search(query, kind=kind)

    def store_report(self, incoming: IncomingReport) -> StoredReport:
        report = ScoutReport(
            scout=incoming.scout,
            target=redact_within(incoming.target, 'target', self.options.name_limit),
            report=redact_within(incoming.report, 'report', self.options.report_limit),
        )
        report_id = self.scouts.add_report(report)
        written = Written(kind='scout-report', reference=str(report_id), text=report.report)
        return StoredReport(id=report_id, duplicates=tuple(self.similarity.record_all([written])))

    def has_report_of(self, incoming: IncomingReport) -> bool:
        report = ScoutReport(
            scout=incoming.scout,
            target=redact(incoming.target),
            report=redact(incoming.report),
        )
        return self.scouts.has_report(report)
