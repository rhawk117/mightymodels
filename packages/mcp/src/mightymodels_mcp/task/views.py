"""What the task tools return: the rendered text, whether the call advanced, and the records."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.vocabulary.tasks import TaskStatus, Worker
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.tasks import FixRecorded, Readiness
    from mightymodels_core.tasks.records import AttemptCounts, TaskRecord

UNKNOWN_HEAD = 'unknown'
SHORT_HEAD_LENGTH = 12


@dataclass(slots=True, kw_only=True, frozen=True)
class StartOrigin:
    worker: Worker
    head: str | None


class TaskRecordView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: TaskStatus
    owned: tuple[str, ...]
    base: str | None
    commit: str | None
    attempts: dict[Worker, int]
    reasons: tuple[str, ...]


class TaskView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    advanced: bool
    tasks: tuple[TaskRecordView, ...] = ()


def short_head(head: str | None) -> str:
    return UNKNOWN_HEAD if head is None else head[:SHORT_HEAD_LENGTH]


def render_problems(problems: Sequence[str]) -> str:
    return ''.join(f'  - {problem}\n' for problem in problems)


def create_record_view(record: TaskRecord, attempts: AttemptCounts) -> TaskRecordView:
    return TaskRecordView(
        id=record.key,
        status=record.status,
        owned=record.owned,
        base=record.base,
        commit=record.commit,
        attempts=attempts.get(record.key, {}),
        reasons=tuple(record.reasons),
    )


def create_record_views(
    records: Sequence[TaskRecord], attempts: AttemptCounts
) -> tuple[TaskRecordView, ...]:
    return tuple(create_record_view(record, attempts) for record in records)


def render_started(record: TaskRecord, attempts: AttemptCounts, origin: StartOrigin) -> TaskView:
    text = f'{record.key} {record.status} by {origin.worker} from {short_head(origin.head)}\n'
    return TaskView(text=text, advanced=True, tasks=create_record_views([record], attempts))


def render_verified(record: TaskRecord, attempts: AttemptCounts) -> TaskView:
    text = f'{record.key} {record.status}\n{render_problems(record.reasons)}'
    return TaskView(
        text=text,
        advanced=record.status == 'verified',
        tasks=create_record_views([record], attempts),
    )


def render_marked(record: TaskRecord, attempts: AttemptCounts, reason: str) -> TaskView:
    text = f'{record.key} {record.status}: {reason}\n'
    return TaskView(text=text, advanced=True, tasks=create_record_views([record], attempts))


def render_listing(records: Sequence[TaskRecord], attempts: AttemptCounts) -> TaskView:
    views = create_record_views(records, attempts)
    lines = (
        f'{view.id}\t{view.status}\tattempts {view.attempts}\t{"; ".join(view.reasons)}\n'
        for view in views
    )
    text = ''.join(lines) or 'no tasks started\n'
    return TaskView(text=text, advanced=True, tasks=views)


def render_readiness(readiness: Readiness, attempts: AttemptCounts, head: str | None) -> TaskView:
    views = create_record_views(readiness.records, attempts)
    if readiness.problems:
        text = f'not ready\n{render_problems(readiness.problems)}'
        return TaskView(text=text, advanced=False, tasks=views)

    return TaskView(text=f'ready at {short_head(head)}\n', advanced=True, tasks=views)


def render_fix_recorded(task_id: str, recorded: FixRecorded) -> TaskView:
    text = (
        f'{task_id} failed fix {recorded.number} recorded: {recorded.hypothesis}\n'
        f'{recorded.remaining} left\n'
    )
    return TaskView(text=text, advanced=False)
