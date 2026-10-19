"""The values the review repositories hand out and take in: frozen, never a database row.

Every prose field is redacted text, which only `redact` produces, so a secret cannot reach a
review record by the type alone. Keys, sources, severities, kinds, commits, heads, scopes and
models are plain.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import ReadLimit
from mightymodels_core.reviews.errors import (
    UndecidedFindingError,
    UnknownFindingError,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText, RunId, Slug, WriteLimitError
    from mightymodels_core.schemas.reviews import (
        Decision,
        Depth,
        Emphasis,
        EvidenceKind,
        FindingKind,
        FindingSeverity,
        Result,
        Scope,
    )

FINDINGS = ReadLimit(rows=1000, kept='findings')
RUNS_LISTED = ReadLimit(rows=50, kept='review runs')


@dataclass(slots=True, kw_only=True, frozen=True)
class Evidence:
    kind: EvidenceKind
    cite: RedactedText


@dataclass(slots=True, kw_only=True, frozen=True)
class IncomingEvidence:
    kind: EvidenceKind
    cite: str


@dataclass(slots=True, kw_only=True, frozen=True)
class IncomingFinding:
    sources: tuple[str, ...]
    severity: FindingSeverity
    kind: FindingKind
    security: bool
    title: str
    location: str
    fix: str
    verify: str
    evidence: IncomingEvidence | None


@dataclass(slots=True, kw_only=True, frozen=True)
class FindingRecord:
    key: str
    sources: tuple[str, ...]
    severity: FindingSeverity
    kind: FindingKind
    security: bool
    title: RedactedText
    location: RedactedText
    fix: RedactedText
    verify: RedactedText
    evidence: Evidence | None
    conflict: RedactedText | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewRunRecord:
    run_id: RunId
    slug: Slug | None
    scope: Scope
    base: str | None
    head: str | None
    depth: Depth
    emphasis: Emphasis
    weights: Mapping[str, float]
    personas: tuple[str, ...]
    models: Mapping[str, str | None]
    created_at: datetime


@dataclass(slots=True, kw_only=True, frozen=True)
class DecidedFinding:
    finding_key: str
    decision: Decision
    reason: RedactedText
    by: RedactedText
    at: datetime


@dataclass(slots=True, kw_only=True, frozen=True)
class ResolvedFinding:
    finding_key: str
    result: Result
    commit: str
    reason: RedactedText
    at: datetime


def finding_write_error(
    run: RunId, held_keys: Collection[str], findings: Sequence[FindingRecord]
) -> WriteLimitError | None:
    total = len(set(held_keys) | {finding.key for finding in findings})
    return FINDINGS.write_error(total, owner=f'run {run}')


def unknown_finding_error(
    run: RunId, finding_keys: Collection[str], decided: Sequence[DecidedFinding]
) -> UnknownFindingError | None:
    for disposition in decided:
        if disposition.finding_key not in finding_keys:
            return UnknownFindingError(run=run, finding_key=disposition.finding_key)

    return None


def undecided_finding_error(
    run: RunId, decided_keys: Collection[str], resolved: ResolvedFinding
) -> UndecidedFindingError | None:
    if resolved.finding_key in decided_keys:
        return None

    return UndecidedFindingError(run=run, finding_key=resolved.finding_key)
