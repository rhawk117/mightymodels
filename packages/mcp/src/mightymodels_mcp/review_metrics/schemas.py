"""The review_metrics request: the run to measure for and how the summary is cut.

A package is the first path part by default and fifty entries are
listed. The measured path and the report's location are derived, so the request names neither.
"""

from typing import Annotated

from pydantic import Field

from mightymodels_mcp.review.schemas import RunIdField
from mightymodels_mcp.server.requests import RequestModel

from .domain import DEFAULT_MAX_LISTED, DEFAULT_PACKAGE_DEPTH

type Depth = Annotated[int, Field(ge=1)]
type Count = Annotated[int, Field(ge=1)]


class ReviewMetricsRequest(RequestModel):
    run_id: RunIdField
    package_depth: Depth = DEFAULT_PACKAGE_DEPTH
    max_listed: Count = DEFAULT_MAX_LISTED
