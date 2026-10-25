"""The request base every tool input derives from, and the fields shared across concepts.

The SDK validates tool arguments with an `ArgModelBase` and passes each top-level field to the
tool function as its own keyword. A request model is that argument model: it hands itself over
whole as `request`, so the published input schema is the request model's own fields.
"""

from typing import Annotated, Any, override

from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase
from mightymodels_core.primitives import Slug, parse_slug
from pydantic import AfterValidator, ConfigDict

REQUEST_ARGUMENT = 'request'


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
