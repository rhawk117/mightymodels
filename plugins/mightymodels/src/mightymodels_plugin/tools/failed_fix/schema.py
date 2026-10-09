"""Arguments of the `failed_fix` tool, the one tool an engineer is allowed to call."""

from enum import StrEnum, auto

from mightymodels_plugin.tools.request import ProseText, RequestModel
from mightymodels_plugin.tools.task.schema import TaskId


class FailedFixAction(StrEnum):
    RECORD = auto()


class TaskFailedFix(RequestModel):
    hypothesis: ProseText


class FailedFixPayload(RequestModel):
    task_id: TaskId
    change: TaskFailedFix
