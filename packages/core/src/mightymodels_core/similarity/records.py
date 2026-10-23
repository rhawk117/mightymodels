"""The values the similarity repositories hand out and take in: frozen, never a database row.

The text a caller writes and a scout report's target and body are redacted text, which only
`redact` produces, so a secret cannot reach a similarity entry by the type alone. A search query is
never stored and stays a plain string. References, kinds and scouts are plain.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mightymodels_core.primitives import RedactedText
    from mightymodels_core.vocabulary.similarity import Scout, SimilarityKind


@dataclass(slots=True, kw_only=True, frozen=True)
class Written:
    kind: SimilarityKind
    reference: str
    text: RedactedText


@dataclass(slots=True, kw_only=True, frozen=True)
class Match:
    kind: SimilarityKind
    reference: str
    text: RedactedText
    overlap: float


@dataclass(slots=True, kw_only=True, frozen=True)
class Duplicate:
    written: str
    earlier: Match


@dataclass(slots=True, kw_only=True, frozen=True)
class ScoutReport:
    scout: Scout
    target: RedactedText
    report: RedactedText
