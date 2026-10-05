"""The `task` tool: each handler checks the call's arguments and asks the task service.

`ResolvedTasks` is a plain assignment because the SDK does not see a `Resolve` marker behind a
PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.protocol import (
    ActionTool,
    LifespanState,
    MissingArgumentsError,
    ServiceHandler,
    dispatch_to_service,
)
from mightymodels_plugin.tools.task.schema import (
    TaskAction,
    TaskChange,
    TaskId,
    TaskMark,
    TaskStart,
    TaskVerification,
    TaskView,
)
from mightymodels_plugin.tools.task.service import TaskService


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskCall:
    slug: Slug
    task_id: str | None
    change: TaskChange | None


def start_task(tasks: TaskService, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskStart):
        raise MissingArgumentsError(TaskAction.START, 'task_id and a change holding by and owned')
    return tasks.start(call.slug, call.task_id, call.change)


def verify_task(tasks: TaskService, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskVerification):
        raise MissingArgumentsError(TaskAction.VERIFY, 'task_id and a change holding commit')
    return tasks.verify(call.slug, call.task_id, call.change)


def mark_task(tasks: TaskService, call: TaskCall) -> TaskView:
    if call.task_id is None or not isinstance(call.change, TaskMark):
        raise MissingArgumentsError(TaskAction.MARK, 'task_id and a change holding to and reason')
    return tasks.mark(call.slug, call.task_id, call.change)


def show_tasks(tasks: TaskService, call: TaskCall) -> TaskView:
    return tasks.show(call.slug)


def gate_readiness(tasks: TaskService, call: TaskCall) -> TaskView:
    return tasks.ready(call.slug)


def lifespan_tasks(ctx: Context[LifespanState]) -> TaskService:
    return ctx.request_context.lifespan_context.tasks


ResolvedTasks = Annotated[TaskService, Resolve(lifespan_tasks)]


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskTool:
    handlers: Mapping[TaskAction, ServiceHandler[TaskService, TaskCall, TaskView]]

    def task(  # noqa: PLR0913 - four arguments are the schema the model sees and the SDK injects the fifth
        self,
        action: TaskAction,
        slug: Slug,
        *,
        task_id: TaskId | None = None,
        change: TaskChange | None = None,
        tasks: ResolvedTasks,
    ) -> TaskView:
        """Start, mark, verify or list tasks, and gate the ticket on readiness."""
        call = TaskCall(slug=slug, task_id=task_id, change=change)
        return dispatch_to_service(self.handlers, action, call, service=tasks)


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
task_action_tool: ActionTool[TaskAction, TaskService, TaskCall, TaskView] = task_tool
