"""The request base every tool input derives from, and the fields shared across concepts.

The SDK validates tool arguments with an `ArgModelBase` and passes each top-level field to the
tool function as its own keyword. A request model is that argument model: it hands itself over
whole as `request`, so the published input schema is the request model's own fields.
"""

from typing import Annotated, Any, override

from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase
from mightymodels_core.git.revisions import revision_error
from mightymodels_core.primitives import Slug, parse_slug
from pydantic import AfterValidator, ConfigDict, StringConstraints

REQUEST_ARGUMENT = 'request'
USER_APPROVER = 'user'
NAME_LIMIT = 255
PROSE_LIMIT = 4000

type NameText = Annotated[str, StringConstraints(max_length=NAME_LIMIT)]
type ProseText = Annotated[str, StringConstraints(max_length=PROSE_LIMIT)]


class RequestModel(ArgModelBase):
    model_config = ConfigDict(extra='forbid', frozen=True, arbitrary_types_allowed=False)

    @override
    def model_dump_one_level(self) -> dict[str, Any]:
        return {REQUEST_ARGUMENT: self}


def validate_slug(raw: str) -> Slug:
    parsed = parse_slug(raw)
    if isinstance(parsed, str):
        return parsed

    message = str(parsed)
    raise ValueError(message) from parsed


type SlugField = Annotated[Slug, AfterValidator(validate_slug)]


def validate_revision(raw: str) -> str:
    refused = revision_error(raw)
    if refused is None:
        return raw

    message = str(refused)
    raise ValueError(message) from refused


type RevisionField = Annotated[
    str, StringConstraints(max_length=NAME_LIMIT), AfterValidator(validate_revision)
]
