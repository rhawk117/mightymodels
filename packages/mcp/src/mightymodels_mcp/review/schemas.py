"""The review run tools' requests.

A run id is held to core's pattern by its parser and publishes no `pattern` of its own, because
core's patterns end in an end-of-string anchor that pydantic's Rust regex and JS clients read
differently. Whether a start names what its scope needs, and whether the weights and persona fit,
stay core's rules.
"""

from typing import Annotated, Literal

from mightymodels_core.primitives import RunId, parse_run_id
from mightymodels_core.vocabulary.reviews import Depth, Emphasis, Persona, Scope
from pydantic import AfterValidator

from mightymodels_mcp.server.requests import RequestModel, RevisionField, SlugField

type ReportShape = Literal['full', 'comment']


def validate_run_id(raw: str) -> RunId:
    parsed = parse_run_id(raw)
    if isinstance(parsed, str):
        return parsed

    message = str(parsed)
    raise ValueError(message) from parsed


type RunIdField = Annotated[RunId, AfterValidator(validate_run_id)]


class ReviewStartRequest(RequestModel):
    scope: Scope | None = None
    depth: Depth | None = None
    emphasis: Emphasis | None = None
    slug: SlugField | None = None
    base: RevisionField | None = None
    weights: dict[Persona, float] | None = None
    persona: Persona | None = None


class ReviewOverrideRequest(RequestModel):
    run_id: RunIdField


class ReviewAddRequest(RequestModel):
    run_id: RunIdField
    persona: Persona


class ReviewGateRequest(RequestModel):
    run_id: RunIdField


class ReviewReportRequest(RequestModel):
    run_id: RunIdField
    shape: ReportShape = 'full'


class ReviewListRequest(RequestModel):
    pass
