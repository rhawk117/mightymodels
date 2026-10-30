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
    target: str | None = Field(
        default=None,
        description='A path inside the repository to measure; omit it to measure all of it.',
    )
    since: Since | None = Field(
        default=None,
        description='Only commits after this date; max_commits and baseline_ref still apply.',
    )
    baseline_ref: BaselineRef | None = Field(
        default=None,
        description='Only commits after this revision up to HEAD; omit it to read back from HEAD.',
    )
    max_commits: Count = Field(
        default=DEFAULT_MAX_COMMITS,
        description='The most commits read; all_history lifts this cap.',
    )
    all_history: bool = Field(
        default=False,
        description='Read every commit in the window instead of stopping at max_commits.',
    )
    limit: Count = Field(
        default=DEFAULT_LIMIT, description='The most signals listed in the report.'
    )


class CodeChurnRequest(HistoryWindowRequest):
    pass


class CodeHotspotsRequest(HistoryWindowRequest):
    pass


class ChangeCouplingRequest(HistoryWindowRequest):
    min_shared: Count = Field(
        default=DEFAULT_MIN_SHARED,
        description='The fewest commits two files must share to be reported as coupled.',
    )
    max_changeset: Count = Field(
        default=DEFAULT_MAX_CHANGESET,
        description='Commits touching more files than this are skipped as bulk changes.',
    )
