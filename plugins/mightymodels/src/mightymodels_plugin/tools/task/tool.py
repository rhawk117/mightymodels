"""The `task` tool."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.models.task import (
    TaskAction,
    TaskChange,
    TaskId,
    TaskMark,
    TaskStart,
    TaskVerification,
    TaskView,
)
from mightymodels_plugin.services import task as service
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.protocol import (
    ActionHandler,
    MissingArgumentsError,
    ResolvedCheckouts,
    dispatch_action,
)


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskCall:
    slug: Slug
    task_id: str | None
    change: TaskChange | None


def start_task(checkout: Checkout, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskStart):
        raise MissingArgumentsError(TaskAction.START, 'task_id and a change holding by and owned')
    return service.start(checkout, call.slug, task_id=call.task_id, change=call.change)


def verify_task(checkout: Checkout, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskVerification):
        raise MissingArgumentsError(TaskAction.VERIFY, 'task_id and a change holding commit')
    return service.verify(checkout, call.slug, task_id=call.task_id, change=call.change)


def mark_task(checkout: Checkout, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskMark):
        raise MissingArgumentsError(TaskAction.MARK, 'task_id and a change holding to and reason')
    return service.mark(checkout, call.slug, task_id=call.task_id, change=call.change)


def show_tasks(checkout: Checkout, call: TaskCall) -> TaskView:
    return service.show(checkout, call.slug)


def gate_readiness(checkout: Checkout, call: TaskCall) -> TaskView:
    return service.ready(checkout, call.slug)


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskTool:
    handlers: Mapping[TaskAction, ActionHandler[TaskCall, TaskView]]

    def task(  # noqa: PLR0913 - four arguments are the schema the model sees and the SDK injects the fifth
        self,
        action: TaskAction,
        slug: Slug,
        *,
        task_id: TaskId | None = None,
        change: TaskChange | None = None,
        checkouts: ResolvedCheckouts,
    ) -> TaskView:
        """Start, mark, verify or list tasks, and gate the ticket on readiness."""
        call = TaskCall(slug=slug, task_id=task_id, change=change)
        return dispatch_action(self.handlers, action, call, checkouts=checkouts)


task_tool = TaskTool(
    handlers=MappingProxyType(
        {
            TaskAction.START: start_task,
            TaskAction.VERIFY: verify_task,
            TaskAction.MARK: mark_task,
            TaskAction.SHOW: show_tasks,
            TaskAction.READY: gate_readiness,
        }
    )
)
