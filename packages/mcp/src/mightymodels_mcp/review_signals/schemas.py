"""The review_signals requests and results: the history window, each analysis cut and the report.

The date and the revision are held to a plain-value pattern and every count has to be at least
one, so a value that could pass for a git option is refused when the request is built. Each
request holds the history window plus only the fields its report reads.
"""

from typing import Annotated

from pydantic import Field, StringConstraints

from mightymodels_mcp.server.requests import RequestModel

DEFAULT_MAX_COMMITS = 500
DEFAULT_LIMIT = 25
DEFAULT_MIN_SHARED = 3
DEFAULT_MAX_CHANGESET = 50

type Since = Annotated[str, StringConstraints(pattern=r'^[0-9A-Za-z][0-9A-Za-z .:+-]*$')]
type BaselineRef = Annotated[str, StringConstraints(pattern=r'^[0-9A-Za-z][0-9A-Za-z._/-]*$')]
type Count = Annotated[int, Field(ge=1)]


class HistoryWindowRequest(RequestModel):
    target: str | None = None
    since: Since | None = None
    baseline_ref: BaselineRef | None = None
    max_commits: Count = DEFAULT_MAX_COMMITS
    all_history: bool = False
    limit: Count = DEFAULT_LIMIT


class CodeChurnRequest(HistoryWindowRequest):
    pass


class CodeHotspotsRequest(HistoryWindowRequest):
    pass


class ChangeCouplingRequest(HistoryWindowRequest):
    min_shared: Count = DEFAULT_MIN_SHARED
    max_changeset: Count = DEFAULT_MAX_CHANGESET
