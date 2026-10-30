"""The review_signals requests and results: the history window, each analysis cut and the report.

Every field reuses the constrained types of `SignalsOptions`, so a date or a revision that could
pass for a git option is refused when the request is built. Each request holds only the fields
its report reads.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from mightymodels_mcp.server.requests import RequestModel

from .options import (
    DEFAULT_LIMIT,
    DEFAULT_MAX_CHANGESET,
    DEFAULT_MAX_COMMITS,
    DEFAULT_MIN_SHARED,
    BaselineRef,
    Count,
    Since,
)


class CodeChurnRequest(RequestModel):
    target: str | None = None
    since: Since | None = None
    baseline_ref: BaselineRef | None = None
    max_commits: Count = DEFAULT_MAX_COMMITS
    all_history: bool = False
    limit: Count = DEFAULT_LIMIT


class CodeHotspotsRequest(CodeChurnRequest):
    pass


class ChangeCouplingRequest(CodeChurnRequest):
    min_shared: Count = DEFAULT_MIN_SHARED
    max_changeset: Count = DEFAULT_MAX_CHANGESET


class Analysis(StrEnum):
    CHURN = 'code-churn'
    COUPLING = 'change-coupling'
    HOTSPOTS = 'code-hotspots'


class ScannedHistory(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    since: str | None
    baseline_ref: str | None
    max_commits: int | None
    commits_scanned: int
    truncated: bool


class Report[Signal](BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    analysis: Analysis
    target: str
    history: ScannedHistory
    signals: list[Signal]
    limitations: list[str]
