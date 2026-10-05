"""The `task` tool."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.models.slug import Slug
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
from mightymodels_plugin.tools.edge import ArgumentsError, tool_checkout


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskCall:
    slug: Slug
    task_id: str | None
    change: TaskChange | None


type TaskHandler = Callable[[Checkout, TaskCall], TaskView]


def start(checkout: Checkout, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskStart):
        raise ArgumentsError(TaskAction.START, 'task_id and a change holding by and owned')
    return service.start(checkout, call.slug, task_id=call.task_id, change=call.change)


def verify(checkout: Checkout, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskVerification):
        raise ArgumentsError(TaskAction.VERIFY, 'task_id and a change holding commit')
    return service.verify(checkout, call.slug, task_id=call.task_id, change=call.change)


def mark(checkout: Checkout, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskMark):
        raise ArgumentsError(TaskAction.MARK, 'task_id and a change holding to and reason')
    return service.mark(checkout, call.slug, task_id=call.task_id, change=call.change)


def show(checkout: Checkout, call: TaskCall) -> TaskView:
    return service.show(checkout, call.slug)


def ready(checkout: Checkout, call: TaskCall) -> TaskView:
    return service.ready(checkout, call.slug)


HANDLERS: Mapping[TaskAction, TaskHandler] = MappingProxyType(
    {
        TaskAction.START: start,
        TaskAction.VERIFY: verify,
        TaskAction.MARK: mark,
        TaskAction.SHOW: show,
        TaskAction.READY: ready,
    }
)


def task(
    action: TaskAction,
    slug: Slug,
    *,
    task_id: TaskId | None = None,
    change: TaskChange | None = None,
) -> TaskView:
    """Start, mark, verify or list tasks, and gate the ticket on readiness."""
    with tool_checkout() as checkout:
        return HANDLERS[action](checkout, TaskCall(slug=slug, task_id=task_id, change=change))
