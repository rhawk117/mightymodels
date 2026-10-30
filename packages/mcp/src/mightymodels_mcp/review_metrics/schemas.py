"""The review_metrics request: the run to measure for and how the summary is cut.

The defaults are the old command line's: a package is the first path part and fifty entries are
listed. The measured path and the report's location are derived, so the request names neither.
"""

from typing import Annotated

from pydantic import Field

from mightymodels_mcp.review.schemas import RunIdField
from mightymodels_mcp.server.requests import RequestModel

DEFAULT_PACKAGE_DEPTH = 1
DEFAULT_MAX_LISTED = 50


class ReviewMetricsRequest(RequestModel):
    run_id: RunIdField
    package_depth: Annotated[int, Field(ge=1)] = DEFAULT_PACKAGE_DEPTH
    max_listed: Annotated[int, Field(ge=1)] = DEFAULT_MAX_LISTED
