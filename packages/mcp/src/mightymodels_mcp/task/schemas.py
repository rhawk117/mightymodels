"""The task tools' requests, and the core requests they turn into.

A task id is held to core's pattern and length. A request only needs one criterion and one owned
file; a task above the warning bounds is started and its answer carries a warning.
"""

from typing import Annotated, Literal, Self

from mightymodels_core.primitives import TaskId, parse_task_id
from mightymodels_core.tasks import MarkRequest, StartRequest
from mightymodels_core.vocabulary.tasks import ArchitectMode, Worker
from pydantic import AfterValidator, Field, model_validator

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


class TaskDeclareRequest(RequestModel):
    slug: SlugField
    task_ids: tuple[TaskIdField, ...] = Field(
        min_length=1, description='The plan task ids to record as pending, such as T1 and T2.'
    )


class TaskVerifyRequest(RequestModel):
    slug: SlugField
    task_id: TaskIdField
    commit: RevisionField = Field(description='The commit the worker reports for the task.')
    verdict: Literal['verified', 'failed', 'blocked'] = Field(
        description='The primary verdict on the task; git facts never change it.'
    )
    reason: ProseText | None = Field(
        default=None,
        description='Why the task failed or is blocked; required for those, refused for verified.',
    )

    @model_validator(mode='after')
    def require_reason_unless_verified(self) -> Self:
        if self.verdict == 'verified' and self.reason is not None:
            message = 'a verified task takes no reason'
            raise ValueError(message)

        if self.verdict != 'verified' and not (self.reason or '').strip():
            message = f'a {self.verdict} task needs a reason'
            raise ValueError(message)

        return self


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
    )


def create_mark_request(request: TaskMarkRequest) -> MarkRequest:
    return MarkRequest(task_key=request.task_id, to=request.to, reason=request.reason)
