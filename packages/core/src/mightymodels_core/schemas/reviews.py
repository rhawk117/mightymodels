"""Review runs, their findings, and the dispositions and outcomes recorded against findings."""

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from msgspec import Struct

from mightymodels_core.database import Command, Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


type Scope = Literal['diff', 'branch', 'ticket', 'codebase']


type Depth = Literal['quick', 'standard', 'deep']


type Emphasis = Literal['release-readiness', 'maintainability', 'balanced', 'custom']


type FindingSeverity = Literal['Blocker', 'Critical', 'High', 'Medium', 'Low']


type FindingKind = Literal['defect', 'quality']


type EvidenceKind = Literal['metric', 'idiom', 'convention']


type Decision = Literal['fix', 'defer', 'accept-risk', 'dismiss']


type Result = Literal['fixed', 'failed', 'blocked']


class RecordReviewRunParams(Struct, frozen=True, kw_only=True):
    repository_id: int
    run_key: str
    ticket_key: str | None
    scope: Scope
    base: str | None
    head: str | None
    depth: Depth
    emphasis: Emphasis
    weights: dict[str, float]
    personas: list[str]
    models: dict[str, str | None]
    created_at: datetime


class RecordReviewModelsParams(Struct, frozen=True, kw_only=True):
    repository_id: int
    run_key: str
    models: dict[str, str | None]


class ReviewRunParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    run_key: str


class LatestReviewRunsParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    limit: int


class TicketReviewRunParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    ticket_key: str


class UpsertReviewFindingParams(Struct, frozen=True, kw_only=True):
    review_run_id: int
    finding_key: str
    sources: list[str]
    severity: FindingSeverity
    kind: FindingKind
    security: bool
    title: str
    location: str
    fix: str
    verify: str
    evidence_kind: EvidenceKind | None
    evidence_cite: str | None
    conflict: str | None


class RunParams(Struct, frozen=True, kw_only=True, gc=False):
    review_run_id: int


class RunLimitParams(Struct, frozen=True, kw_only=True, gc=False):
    review_run_id: int
    limit: int


class UpsertReviewDispositionParams(Struct, frozen=True, kw_only=True, gc=False):
    review_run_id: int
    finding_key: str
    decision: Decision
    reason: str
    by: str
    at: datetime


class UpsertReviewOutcomeParams(Struct, frozen=True, kw_only=True, gc=False):
    review_run_id: int
    finding_key: str
    result: Result
    commit: str
    reason: str
    at: datetime


class FindingKeysParams(Struct, frozen=True, kw_only=True):
    review_run_id: int
    finding_keys: list[str]


class ReviewRunIdRow(Struct, frozen=True, kw_only=True, gc=False):
    id: int


class ReviewRunRow(Struct, frozen=True, kw_only=True):
    id: int
    run_key: str
    ticket_key: str | None
    scope: Scope
    base: str | None
    head: str | None
    depth: Depth
    emphasis: Emphasis
    weights: dict[str, float]
    personas: list[str]
    models: dict[str, str | None]
    created_at: datetime


class ReviewFindingRow(Struct, frozen=True, kw_only=True):
    finding_key: str
    sources: list[str]
    severity: FindingSeverity
    kind: FindingKind
    security: bool
    title: str
    location: str
    fix: str
    verify: str
    evidence_kind: EvidenceKind | None
    evidence_cite: str | None
    conflict: str | None


class ReviewDispositionRow(Struct, frozen=True, kw_only=True, gc=False):
    finding_key: str
    decision: Decision
    reason: str
    by: str
    at: datetime


class ReviewOutcomeRow(Struct, frozen=True, kw_only=True, gc=False):
    finding_key: str
    result: Result
    commit: str
    reason: str
    at: datetime


class ReviewCountRow(Struct, frozen=True, kw_only=True, gc=False):
    count: int


RECORD_REVIEW_RUN = Query(
    name='record_review_run', params=RecordReviewRunParams, row=ReviewRunIdRow
)
RECORD_REVIEW_MODELS = Command(name='record_review_models', params=RecordReviewModelsParams)
REVIEW_RUN = Query(name='review_run', params=ReviewRunParams, row=ReviewRunRow)
LATEST_REVIEW_RUNS = Query(
    name='latest_review_runs', params=LatestReviewRunsParams, row=ReviewRunRow
)
LATEST_REVIEW_RUN_OF_TICKET = Query(
    name='latest_review_run_of_ticket', params=TicketReviewRunParams, row=ReviewRunRow
)
UPSERT_REVIEW_FINDING = Command(name='upsert_review_finding', params=UpsertReviewFindingParams)
REVIEW_FINDINGS_OF_RUN = Query(
    name='review_findings_of_run', params=RunLimitParams, row=ReviewFindingRow
)
REVIEW_FINDING_COUNT = Query(name='review_finding_count', params=RunParams, row=ReviewCountRow)
UPSERT_REVIEW_DISPOSITION = Command(
    name='upsert_review_disposition', params=UpsertReviewDispositionParams
)
REVIEW_DISPOSITIONS_OF_RUN = Query(
    name='review_dispositions_of_run', params=RunLimitParams, row=ReviewDispositionRow
)
REVIEW_DISPOSITION_COUNT = Query(
    name='review_disposition_count', params=RunParams, row=ReviewCountRow
)
DELETE_REVIEW_DISPOSITIONS = Command(name='delete_review_dispositions', params=FindingKeysParams)
UPSERT_REVIEW_OUTCOME = Command(name='upsert_review_outcome', params=UpsertReviewOutcomeParams)
REVIEW_OUTCOMES_OF_RUN = Query(
    name='review_outcomes_of_run', params=RunLimitParams, row=ReviewOutcomeRow
)
REVIEW_OUTCOME_COUNT = Query(name='review_outcome_count', params=RunParams, row=ReviewCountRow)
DELETE_REVIEW_OUTCOMES = Command(name='delete_review_outcomes', params=FindingKeysParams)

DECLARATIONS: tuple[Declaration, ...] = (
    RECORD_REVIEW_RUN,
    RECORD_REVIEW_MODELS,
    REVIEW_RUN,
    LATEST_REVIEW_RUNS,
    LATEST_REVIEW_RUN_OF_TICKET,
    UPSERT_REVIEW_FINDING,
    REVIEW_FINDINGS_OF_RUN,
    REVIEW_FINDING_COUNT,
    UPSERT_REVIEW_DISPOSITION,
    REVIEW_DISPOSITIONS_OF_RUN,
    REVIEW_DISPOSITION_COUNT,
    DELETE_REVIEW_DISPOSITIONS,
    UPSERT_REVIEW_OUTCOME,
    REVIEW_OUTCOMES_OF_RUN,
    REVIEW_OUTCOME_COUNT,
    DELETE_REVIEW_OUTCOMES,
)
