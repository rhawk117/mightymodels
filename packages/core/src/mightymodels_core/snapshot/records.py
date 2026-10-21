"""The snapshot read model: the git facts it is given and the record it returns.

The adapter asks git first and passes the answer in as one `RepositoryFacts`, so nothing here runs
git. Every section of the record is a frozen value of plain fields with no wording; the renderer
words them. The record holds no Answers or Subagents section.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from mightymodels_core.git import GitRefusal
    from mightymodels_core.primitives import RunId, Slug, TaskId
    from mightymodels_core.schemas.investigations import EntryKind
    from mightymodels_core.schemas.reviews import Decision, Depth
    from mightymodels_core.schemas.tasks import TaskStatus, Worker
    from mightymodels_core.schemas.tickets import TicketScope, TicketStatus
    from mightymodels_core.tickets.records import Tracker

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(slots=True, kw_only=True, frozen=True)
class RepositoryFacts:
    branch: str | None
    head: str | None
    dirty: tuple[str, ...] | None
    refusal: GitRefusal | None


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketSummary:
    summary: str
    status: TicketStatus
    scope: TicketScope
    tracker: Tracker


@dataclass(slots=True, kw_only=True, frozen=True)
class RepositoryState:
    branch: str | None
    head: str | None
    dirty_count: int | None
    dirty: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskState:
    task: TaskId
    status: str
    attempts: Mapping[Worker, int]
    reasons: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class CheckState:
    key: str
    state: str


@dataclass(slots=True, kw_only=True, frozen=True)
class PassingCommand:
    key: str
    argv: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedAttempt:
    task: TaskId
    to: TaskStatus
    reason: str
    head: str
    at: datetime


@dataclass(slots=True, kw_only=True, frozen=True)
class LedgerLine:
    kind: EntryKind
    text: str
    cite: str | None
    origin: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewDecision:
    finding: str
    decision: Decision
    reason: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ReviewState:
    run: RunId
    depth: Depth
    head: str
    findings: int
    undecided: tuple[str, ...]
    remediation_open: tuple[str, ...]
    decisions: tuple[ReviewDecision, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotRecord:
    slug: Slug
    generated_at: datetime
    ticket: TicketSummary
    repository: RepositoryState
    tasks: tuple[TaskState, ...]
    checks: tuple[CheckState, ...]
    works: tuple[PassingCommand, ...]
    decisions: tuple[LedgerLine, ...]
    open_questions: tuple[LedgerLine, ...]
    do_not_retry: tuple[FailedAttempt, ...]
    review: ReviewState | None
    warnings: tuple[str, ...]
