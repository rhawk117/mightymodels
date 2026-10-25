"""Builders, constants and the harness of the similarity tests."""

from dataclasses import dataclass
from importlib.resources import files
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact
from mightymodels_core.similarity import ScoutReport, Written

if TYPE_CHECKING:
    from mightymodels_core.schemas.scout_reports import Scout
    from mightymodels_core.schemas.similarity import SimilarityKind
    from mightymodels_core.similarity import ScoutReportRepository, SimilarityRepository

SQL = files('mightymodels_core.sql')
STORED_TEXT = 'the retry loop drops the connection pool after a timeout'
STORED_REFERENCE = 'ENT-1'
STORED_TARGET = 'src/api/client.py'


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityHarness:
    similarity: SimilarityRepository
    scouts: ScoutReportRepository


def create_written(reference: str, text: str, *, kind: SimilarityKind = 'ledger-entry') -> Written:
    return Written(kind=kind, reference=reference, text=redact(text))


def create_scout_report(
    target: str = STORED_TARGET, *, scout: Scout = 'code-scout', report: str = 'it is async'
) -> ScoutReport:
    return ScoutReport(scout=scout, target=redact(target), report=redact(report))
