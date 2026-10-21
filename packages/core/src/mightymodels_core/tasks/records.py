"""The values the task repositories hand out and take in: frozen, never a database row.

A `Transition` is one move of a task, written with the change it records and read back as it was
written. An `Attempt` is the worker, the mode and the owned files of one start. A `FailedFix` is the
hypothesis of one fix that did not work. The prose a
transition or a task carries is redacted text, which only `redact` produces, so a secret cannot
reach a task by the type alone.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, get_args

from mightymodels_core.primitives import ReadLimit
from mightymodels_core.vocabulary.tasks import Worker

if TYPE_CHECKING:
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText, TaskId
    from mightymodels_core.vocabulary.tasks import ArchitectMode, TaskStatus

type AttemptCounts = dict[TaskId, dict[Worker, int]]

TASKS = ReadLimit(rows=1000, kept='tasks')
ATTEMPT_COUNTS = ReadLimit(rows=TASKS.rows * len(get_args(Worker.__value__)), kept='attempt counts')
FAILED_FIXES = ReadLimit(rows=3, kept='failed fixes')


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskRecord:
    key: TaskId
    status: TaskStatus
    owned: tuple[str, ...] = ()
    base: str | None = None
    commit: str | None = None
    reasons: tuple[RedactedText, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class Transition:
    task_key: TaskId
    before: TaskStatus
    after: TaskStatus
    reasons: tuple[RedactedText, ...]
    head: str | None
    at: datetime


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedFix:
    task_key: TaskId
    hypothesis: RedactedText
    at: datetime


@dataclass(slots=True, kw_only=True, frozen=True)
class Attempt:
    worker: Worker
    mode: ArchitectMode | None
    owned: tuple[str, ...]
