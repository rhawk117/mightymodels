"""The snapshot tool's request: the slug and how many entries each list keeps."""

from typing import Annotated

from mightymodels_core.snapshot.records import DEFAULT_LIMIT, MAX_LIMIT
from pydantic import Field

from mightymodels_mcp.server.requests import RequestModel, SlugField

type LimitField = Annotated[
    int,
    Field(ge=1, le=MAX_LIMIT, description='How many entries each list in the snapshot keeps.'),
]


class SnapshotTakeRequest(RequestModel):
    slug: SlugField
    limit: LimitField = DEFAULT_LIMIT
