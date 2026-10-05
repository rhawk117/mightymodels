"""Arguments and results of the `review` tool, and the values its service and rendering share.

`FindingInput` is one finding as a persona reports it and `Finding` is one as the run holds it.
`ReviewRun` is a run as it is recorded and read back.

The finding id pattern is published in the tool's schema and names its digits as `[0-9]`, so the
schema and the server accept the same ASCII digits and no others.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels_plugin.routing import Depth
from mightymodels_plugin.run_id import RunId
from mightymodels_plugin.slug import Slug

SOURCE_ID_PATTERN = r'^(MV|UB)-\d+$'
FINDING_ID_PATTERN = r'^F[0-9]+$'

type SourceId = Annotated[str, StringConstraints(pattern=SOURCE_ID_PATTERN)]
type FindingId = Annotated[str, StringConstraints(pattern=FINDING_ID_PATTERN)]
type Approver = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
type Sources = Annotated[tuple[SourceId, ...], Field(min_length=1)]


class ReviewAction(StrEnum):
    START = 'start'
    ADD = 'add'
    GATE = 'gate'
    DISPOSE = 'dispose'
    RESOLVE = 'resolve'
    REPORT = 'report'
    LIST = 'list'


class ReviewScope(StrEnum):
    DIFF = 'diff'
    BRANCH = 'branch'
    TICKET = 'ticket'
    CODEBASE = 'codebase'


class Emphasis(StrEnum):
    RELEASE = 'release-readiness'
    MAINTAINABILITY = 'maintainability'
    BALANCED = 'balanced'
    CUSTOM = 'custom'


class Persona(StrEnum):
    MERGE_VADER = 'merge-vader'
    UNCLE_BOB = 'uncle-bob'


class Severity(StrEnum):
    CRITICAL = 'Critical'
    HIGH = 'High'
    MEDIUM = 'Medium'
    LOW = 'Low'


class ReportedSeverity(StrEnum):
    BLOCKER = 'Blocker'
    CRITICAL = 'Critical'
    HIGH = 'High'
    MEDIUM = 'Medium'
    LOW = 'Low'


class Kind(StrEnum):
    DEFECT = 'defect'
    QUALITY = 'quality'


class EvidenceKind(StrEnum):
    METRIC = 'metric'
    IDIOM = 'idiom'
    CONVENTION = 'convention'


class Decision(StrEnum):
    FIX = 'fix'
    DEFER = 'defer'
    ACCEPT_RISK = 'accept-risk'
    DISMISS = 'dismiss'


class Result(StrEnum):
    FIXED = 'fixed'
    FAILED = 'failed'
    BLOCKED = 'blocked'


class Shape(StrEnum):
    FULL = 'full'
    COMMENT = 'comment'


class Verdict(StrEnum):
    BLOCK = 'BLOCK'
    CONDITIONS = 'MERGE WITH CONDITIONS'
    CLEAR = 'CLEAR'


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    kind: EvidenceKind
    cite: str


class FindingInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    sources: Sources
    severity: ReportedSeverity
    title: str
    location: str
    fix: str
    verify: str
    kind: Kind = Kind.DEFECT
    security: bool = False
    evidence: Evidence | None = None


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: FindingId
    sources: Sources
    severity: Severity
    kind: Kind
    security: bool
    title: str
    location: str
    fix: str
    verify: str
    evidence: Evidence | None = None
    conflict: str | None = None


class StartPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    scope: ReviewScope
    depth: Depth
    emphasis: Emphasis
    slug: Slug | None = None
    base: str | None = None
    weights: dict[Persona, float] | None = None
    persona: Persona | None = None


class AddPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    persona: Persona


class Disposition(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    decision: Decision
    reason: str = ''


class DisposePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    by: Approver
    decisions: dict[FindingId, Disposition]


class ResolvePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    finding: FindingId
    result: Result
    commit: str | None = None
    reason: str | None = None


class ReportPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    shape: Shape = Shape.FULL


type ReviewPayload = StartPayload | AddPayload | DisposePayload | ResolvePayload | ReportPayload


class ReviewView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    run_id: str | None = None
    verdict: Verdict | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewRun:
    run_id: RunId
    slug: Slug | None
    scope: ReviewScope
    base: str | None
    head: str | None
    depth: Depth
    emphasis: Emphasis
    weights: Mapping[Persona, float]
    personas: tuple[Persona, ...]
    models: Mapping[str, str | None]
    created_at: str
