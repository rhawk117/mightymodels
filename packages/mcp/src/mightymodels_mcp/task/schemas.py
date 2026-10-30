"""The task tools' requests, and the core requests they turn into.

A task id is held to core's pattern and length. The size bounds on a task (criteria and owned
files) stay core's, which refuses a task that is too large; a request only needs one of each.
"""

from typing import Annotated, Literal

from mightymodels_core.primitives import TaskId, parse_task_id
from mightymodels_core.tasks import MarkRequest, StartRequest
from mightymodels_core.vocabulary.tasks import ArchitectMode, Worker
from pydantic import AfterValidator, Field

from mightymodels_mcp.server.requests import (
    NameText,
    ProseText,
    RequestModel,
    RevisionField,
    SlugField,
)


def validate_task_id(raw: str) -> TaskId:
    parsed = parse_task_id(raw)
    if isinstance(parsed, str):
        return parsed

    message = str(parsed)
    raise ValueError(message) from parsed


type TaskIdField = Annotated[
    TaskId,
    AfterValidator(validate_task_id),
    Field(description='The task id: T, C or R and a number, such as T3 or R1.'),
]


class TaskStartRequest(RequestModel):
    slug: SlugField
    task_id: TaskIdField
    by: Worker = Field(description='The worker the task is started for.')
    owned: tuple[ProseText, ...] = Field(
        min_length=1, description='The files the worker may edit, one path per entry.'
    )
    acceptance: tuple[NameText, ...] = Field(
        min_length=1, description='The acceptance criteria the task must meet, one per entry.'
    )
    mode: ArchitectMode | None = Field(
        default=None, description='The architect mode; pass it only when the worker is architect.'
    )
    too_large_approved_by: Literal['user'] | None = Field(
        default=None,
        description='Pass user only after the user approved starting a task above the size bounds.',
    )


class TaskVerifyRequest(RequestModel):
    slug: SlugField
    task_id: TaskIdField
    commit: RevisionField = Field(description='The commit the worker reports for the task.')
    assertions: dict[ProseText, ProseText] = Field(
        default_factory=dict,
        description='Evidence for criteria no contract command checks, as criterion to evidence.',
    )


class TaskMarkRequest(RequestModel):
    slug: SlugField
    task_id: TaskIdField
    to: Literal['failed', 'blocked', 'superseded'] = Field(
        description='The state to mark the task as.'
    )
    reason: ProseText = Field(description='Why the task is marked, kept in its history.')


class TaskRequest(RequestModel):
    slug: SlugField


class FailedFixRequest(RequestModel):
    slug: SlugField
    task_id: TaskIdField
    hypothesis: ProseText = Field(description='The cause the failed fix assumed, in one sentence.')


def create_start_request(request: TaskStartRequest, head: str | None) -> StartRequest:
    return StartRequest(
        task_key=request.task_id,
        worker=request.by,
        mode=request.mode,
        owned=request.owned,
        acceptance_count=len(request.acceptance),
        head=head,
        too_large_approved=request.too_large_approved_by is not None,
    )


def create_mark_request(request: TaskMarkRequest) -> MarkRequest:
    return MarkRequest(task_key=request.task_id, to=request.to, reason=request.reason)
