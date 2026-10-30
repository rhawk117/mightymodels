"""The review_signals requests: the history window and the cut each analysis reads.

Every field reuses the constrained types of `SignalsOptions`, so a date or a revision that could
pass for a git option is refused when the request is built. Each request holds only the fields
its report reads.
"""

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
