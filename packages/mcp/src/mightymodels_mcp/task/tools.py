"""The task tools: thin async handlers over the sync use cases, and their registration.

task_start and task_ready ask git only for HEAD. task_verify gathers the verification facts
between a read unit and a write unit, so the database is never held across an `await`.
task_show, task_mark and failed_fix_record never ask git.
"""

from typing import TYPE_CHECKING

from mightymodels_core.workspace import workspace_at

from mightymodels_mcp.server.annotations import MARKS, READS, WRITES
from mightymodels_mcp.server.registration import ToolSpec, open_tool_state, register_specs

from .gate_facts import VerificationSources, gather_verification
from .schemas import (
    FailedFixRequest,
    TaskMarkRequest,
    TaskRequest,
    TaskStartRequest,
    TaskVerifyRequest,
)
from .use_cases import (
    check_ready,
    create_task_work,
    mark_task,
    prepare_verification,
    record_failed_fix,
    show_tasks,
    start_task,
    verify_task,
)
from .views import TaskView

if TYPE_CHECKING:
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext


async def task_start(request: TaskStartRequest, ctx: ToolContext) -> TaskView:
    """Start a task for a worker on the files it owns."""
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        return start_task(create_task_work(state), request, head)


async def task_verify(request: TaskVerifyRequest, ctx: ToolContext) -> TaskView:
    """Verify a task against the reported commit, its contract receipts and its brief."""
    async with open_tool_state(ctx) as state:
        work = create_task_work(state)
        seen = prepare_verification(work, request.slug, request.task_id)
        sources = VerificationSources(
            git=state.git, workspace=workspace_at(state.checkout.toplevel)
        )
        verification = await gather_verification(sources, seen, request)
        return verify_task(work, request.slug, verification)


async def task_mark(request: TaskMarkRequest, ctx: ToolContext) -> TaskView:
    """Mark a task failed, blocked or superseded, with the reason."""
    async with open_tool_state(ctx) as state:
        return mark_task(create_task_work(state), request)


async def task_show(request: TaskRequest, ctx: ToolContext) -> TaskView:
    """Show the tasks of a ticket with their attempts."""
    async with open_tool_state(ctx) as state:
        return show_tasks(create_task_work(state), request.slug)


async def task_ready(request: TaskRequest, ctx: ToolContext) -> TaskView:
    """Say whether the tasks of a ticket are ready to close at the current HEAD."""
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        return check_ready(create_task_work(state), request.slug, head)


async def failed_fix_record(request: FailedFixRequest, ctx: ToolContext) -> TaskView:
    """Record a fix that failed, with the hypothesis it tested."""
    async with open_tool_state(ctx) as state:
        return record_failed_fix(create_task_work(state), request)


TASK_TOOLS = (
    ToolSpec(
        name='task_start',
        title='Start a task',
        annotations=WRITES,
        icon='task',
        request_model=TaskStartRequest,
        result_model=TaskView,
        handler=task_start,
    ),
    ToolSpec(
        name='task_verify',
        title='Verify a task',
        annotations=WRITES,
        icon='task',
        request_model=TaskVerifyRequest,
        result_model=TaskView,
        handler=task_verify,
    ),
    ToolSpec(
        name='task_mark',
        title='Mark a task',
        annotations=MARKS,
        icon='task',
        request_model=TaskMarkRequest,
        result_model=TaskView,
        handler=task_mark,
    ),
    ToolSpec(
        name='task_show',
        title='Show the tasks',
        annotations=READS,
        icon='task',
        request_model=TaskRequest,
        result_model=TaskView,
        handler=task_show,
    ),
    ToolSpec(
        name='task_ready',
        title='Check the tasks are ready',
        annotations=READS,
        icon='task',
        request_model=TaskRequest,
        result_model=TaskView,
        handler=task_ready,
    ),
    ToolSpec(
        name='failed_fix_record',
        title='Record a failed fix',
        annotations=WRITES,
        icon='failed_fix',
        request_model=FailedFixRequest,
        result_model=TaskView,
        handler=failed_fix_record,
    ),
)


def register_task_tools(catalog: ToolCatalog) -> ToolCatalog:
    return register_specs(catalog, TASK_TOOLS)
