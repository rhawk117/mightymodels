"""The task tools: thin async handlers over the sync use cases, and their registration.

task_start and task_ready ask git only for HEAD. task_verify gathers the verification facts
between a read unit and a write unit, so the database is never held across an `await`.
task_show, task_mark and failed_fix_record never ask git.
"""

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations
from mightymodels_core.workspace import workspace_at

from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolDefinition

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
    from contextlib import AbstractAsyncContextManager

    from mightymodels_core.edge import OpenState

    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext

WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
MARKS = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)


def open_state(ctx: ToolContext) -> AbstractAsyncContextManager[OpenState]:
    return ctx.request_context.lifespan_context.state.open()


async def task_start(request: TaskStartRequest, ctx: ToolContext) -> TaskView:
    """Start a task for a worker on the files it owns."""
    async with open_state(ctx) as state:
        head = await state.git.resolve_head()
        return start_task(create_task_work(state), request, head)


async def task_verify(request: TaskVerifyRequest, ctx: ToolContext) -> TaskView:
    """Verify a task against the reported commit, its contract receipts and its brief."""
    async with open_state(ctx) as state:
        work = create_task_work(state)
        seen = prepare_verification(work, request.slug, request.task_id)
        sources = VerificationSources(
            git=state.git, workspace=workspace_at(state.checkout.toplevel)
        )
        verification = await gather_verification(sources, seen, request)
        return verify_task(work, request.slug, verification)


async def task_mark(request: TaskMarkRequest, ctx: ToolContext) -> TaskView:
    """Mark a task failed, blocked or superseded, with the reason."""
    async with open_state(ctx) as state:
        return mark_task(create_task_work(state), request)


async def task_show(request: TaskRequest, ctx: ToolContext) -> TaskView:
    """Show the tasks of a ticket with their attempts."""
    async with open_state(ctx) as state:
        return show_tasks(create_task_work(state), request.slug)


async def task_ready(request: TaskRequest, ctx: ToolContext) -> TaskView:
    """Say whether the tasks of a ticket are ready to close at the current HEAD."""
    async with open_state(ctx) as state:
        head = await state.git.resolve_head()
        return check_ready(create_task_work(state), request.slug, head)


async def failed_fix_record(request: FailedFixRequest, ctx: ToolContext) -> TaskView:
    """Record a fix that failed, with the hypothesis it tested."""
    async with open_state(ctx) as state:
        return record_failed_fix(create_task_work(state), request)


def register_task_tools(catalog: ToolCatalog) -> ToolCatalog:
    icon = load_icon('task')
    start = ToolDefinition(
        name='task_start',
        title='Start a task',
        annotations=WRITES,
        icon=icon,
        request_model=TaskStartRequest,
        result_model=TaskView,
        handler=task_start,
    )
    verify = ToolDefinition(
        name='task_verify',
        title='Verify a task',
        annotations=WRITES,
        icon=icon,
        request_model=TaskVerifyRequest,
        result_model=TaskView,
        handler=task_verify,
    )
    mark = ToolDefinition(
        name='task_mark',
        title='Mark a task',
        annotations=MARKS,
        icon=icon,
        request_model=TaskMarkRequest,
        result_model=TaskView,
        handler=task_mark,
    )
    show = ToolDefinition(
        name='task_show',
        title='Show the tasks',
        annotations=READS,
        icon=icon,
        request_model=TaskRequest,
        result_model=TaskView,
        handler=task_show,
    )
    ready = ToolDefinition(
        name='task_ready',
        title='Check the tasks are ready',
        annotations=READS,
        icon=icon,
        request_model=TaskRequest,
        result_model=TaskView,
        handler=task_ready,
    )
    fix = ToolDefinition(
        name='failed_fix_record',
        title='Record a failed fix',
        annotations=WRITES,
        icon=load_icon('failed_fix'),
        request_model=FailedFixRequest,
        result_model=TaskView,
        handler=failed_fix_record,
    )
    opened = catalog.register(start).register(verify).register(mark)
    return opened.register(show).register(ready).register(fix)
