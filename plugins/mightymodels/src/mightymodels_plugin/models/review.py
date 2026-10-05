"""Arguments and results of the `review` tool, and the typed finding batch its service takes."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels_plugin.routing import Depth
from mightymodels_plugin.slug import Slug

SOURCE_ID_PATTERN = r'^(MV|UB)-\d+$'
FINDING_ID_PATTERN = r'^F\d+$'

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
