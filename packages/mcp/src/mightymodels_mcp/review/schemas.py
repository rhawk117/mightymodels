"""The review tools' requests: the run tools', and the decision tools' dispose and resolve.

A run id is held to core's pattern by its parser and publishes no `pattern` of its own, because
core's patterns end in an end-of-string anchor that pydantic's Rust regex and JS clients read
differently. Whether a start names what its scope needs, and whether the weights and persona fit,
stay core's rules, as do whether a decision has the reason it needs and whether a commit is a
plain revision.
"""

from typing import Annotated, Literal, Self

from mightymodels_core.primitives import RunId, parse_run_id
from mightymodels_core.vocabulary.reviews import Decision, Depth, Emphasis, Persona, Result, Scope
from pydantic import AfterValidator, Field, model_validator

from mightymodels_mcp.server.requests import (
    NameText,
    ProseText,
    RequestModel,
    RevisionField,
    SlugField,
)

type ReportShape = Literal['full', 'comment']


def validate_run_id(raw: str) -> RunId:
    parsed = parse_run_id(raw)
    if isinstance(parsed, str):
        return parsed

    message = str(parsed)
    raise ValueError(message) from parsed


type RunIdField = Annotated[
    RunId,
    AfterValidator(validate_run_id),
    Field(description='The review run id, as review_start printed it.'),
]


class ReviewStartRequest(RequestModel):
    scope: Scope | None = Field(
        default=None, description='What the review reads; omit it and the user is asked.'
    )
    depth: Depth | None = Field(
        default=None,
        description='How many reviewers read the scope; omit it and the user is asked.',
    )
    emphasis: Emphasis | None = Field(
        default=None,
        description='Which reviewer weighs most, or custom; omit it and the user is asked.',
    )
    slug: SlugField | None = Field(
        default=None, description='The ticket the review belongs to; the ticket scope requires it.'
    )
    base: RevisionField | None = Field(
        default=None,
        description='The revision a branch or ticket scope is reviewed against; they require it.',
    )
    weights: dict[Persona, float] | None = Field(
        default=None,
        description='Each persona to its weight when emphasis is custom; they must sum to one.',
    )
    persona: Persona | None = Field(
        default=None, description='The one reviewer to run when the depth is quick.'
    )


class ReviewOverrideRequest(RequestModel):
    run_id: RunIdField


class ReviewAddRequest(RequestModel):
    run_id: RunIdField
    persona: Persona = Field(description='The reviewer whose report is read and recorded.')


class ReviewGateRequest(RequestModel):
    run_id: RunIdField


class ReviewReportRequest(RequestModel):
    run_id: RunIdField
    shape: ReportShape = Field(
        default='full',
        description='Full renders the whole report; comment renders a review comment.',
    )


class ReviewListRequest(RequestModel):
    pass


class Disposition(RequestModel):
    decision: Decision = Field(description='What is done with the finding.')
    reason: ProseText = Field(
        default='', description='Why the finding is decided this way; some decisions require it.'
    )


class ReviewDisposeRequest(RequestModel):
    run_id: RunIdField
    decisions: dict[NameText, Disposition] | None = Field(
        default=None,
        description='Each finding id to its disposition; omit it and the user is asked.',
    )
    by: NameText = Field(
        default='', description='Who approved the decisions; required when decisions are given.'
    )

    @model_validator(mode='after')
    def require_approver_with_decisions(self) -> Self:
        if self.decisions is not None and not self.by.strip():
            message = 'by is required when decisions are given'
            raise ValueError(message)

        return self


class ReviewResolveRequest(RequestModel):
    run_id: RunIdField
    finding: NameText = Field(description='The id of the finding being resolved.')
    result: Result = Field(description='How the finding was resolved.')
    commit: NameText | None = Field(
        default=None, description='The commit that resolved the finding, as a plain revision.'
    )
    reason: ProseText | None = Field(
        default=None, description='Why the finding is resolved this way, where the result needs it.'
    )
