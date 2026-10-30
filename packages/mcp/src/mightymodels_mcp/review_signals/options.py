"""What a review-signals call asks for, with the checks every value passes before git is launched.

The date and the revision are held to a plain-value pattern and every count has to be at least
one. A value that fails is refused when the model is built.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DEFAULT_MAX_COMMITS = 500
DEFAULT_LIMIT = 25
DEFAULT_MIN_SHARED = 3
DEFAULT_MAX_CHANGESET = 50

type Since = Annotated[str, StringConstraints(pattern=r'^[0-9A-Za-z][0-9A-Za-z .:+-]*$')]
type BaselineRef = Annotated[str, StringConstraints(pattern=r'^[0-9A-Za-z][0-9A-Za-z._/-]*$')]
type Count = Annotated[int, Field(ge=1)]


class SignalsOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    target: str | None = None
    since: Since | None = None
    baseline_ref: BaselineRef | None = None
    max_commits: Count = DEFAULT_MAX_COMMITS
    all_history: bool = False
    limit: Count = DEFAULT_LIMIT
    min_shared: Count = DEFAULT_MIN_SHARED
    max_changeset: Count = DEFAULT_MAX_CHANGESET
