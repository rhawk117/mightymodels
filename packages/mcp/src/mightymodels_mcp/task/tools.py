"""The task tools: thin async handlers over the sync use cases, and their registration.

task_start and task_ready ask git only for HEAD. task_verify gathers the verification facts
between a read unit and a write unit, so the database is never held across an `await`.
task_show, task_mark and failed_fix_record never ask git.
"""

from typing import TYPE_CHECKING

from mightymodels_mcp.server.annotations import MARKS, READS, REFRESHES, WRITES
from mightymodels_mcp.server.registration import ToolSpec, open_tool_state, register_specs

from .gate_facts import VerificationSources, gather_verification
from .schemas import (
    FailedFixRequest,
    TaskDeclareRequest,
    TaskMarkRequest,
    TaskRequest,
    TaskStartRequest,
    TaskVerifyRequest,
)
from .use_cases import (
    check_ready,
    create_task_work,
    declare_tasks,
    mark_task,
    prepare_verification,
    record_failed_fix,
    show_tasks,
    start_task,
    verify_task,
)
from .views import TaskView, VerifyView

if TYPE_CHECKING:
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext


async def task_declare(request: TaskDeclareRequest, ctx: ToolContext) -> TaskView:
    """Record the plan's tasks as pending. Use once the plan is approved, before the first
    task_start. A task already recorded is left unchanged. Only plan tasks, T and a number, are
    accepted. The next step is task_start for each task.
    """
    async with open_tool_state(ctx) as state:
        return declare_tasks(create_task_work(state), request)


async def task_start(request: TaskStartRequest, ctx: ToolContext) -> TaskView:
    """Start a task for a worker on the files it owns. Use just before dispatching that worker, so
    its owned files and acceptance criteria are on record. A large task starts with a warning to
    split it. A plan task never declared is refused; declare it with task_declare first.
    """
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        return start_task(create_task_work(state), request, head)


async def task_verify(request: TaskVerifyRequest, ctx: ToolContext) -> VerifyView:
    """Record the verdict on a task at a commit: verified, failed or blocked. Use after judging a
    worker's report. The answer reports commit-is-HEAD, base-is-ancestor and files changed outside
    the owned set; none changes the verdict. Failed and blocked need a reason.
    """
    async with open_tool_state(ctx) as state:
        work = create_task_work(state)
        seen = prepare_verification(work, request)
        verification = await gather_verification(VerificationSources(git=state.git), seen, request)
        return verify_task(work, request.slug, verification)


async def task_mark(request: TaskMarkRequest, ctx: ToolContext) -> TaskView:
    """Mark a task failed, blocked or superseded, with the reason. Use when a worker reports it
    cannot finish or the plan changed. To record the verdict on finished work, use task_verify.
    """
    async with open_tool_state(ctx) as state:
        return mark_task(create_task_work(state), request)


async def task_show(request: TaskRequest, ctx: ToolContext) -> TaskView:
    """Show the tasks of a ticket with their attempts. Use to see each task's status and history.
    To learn whether the ticket can close, use task_ready.
    """
    async with open_tool_state(ctx) as state:
        return show_tasks(create_task_work(state), request.slug)


async def task_ready(request: TaskRequest, ctx: ToolContext) -> TaskView:
    """Say whether the tasks of a ticket are ready to close at the current HEAD. Use before
    close_check or when finishing. For the commands themselves, use contract_status.
    """
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        return check_ready(create_task_work(state), request.slug, head)


async def failed_fix_record(request: FailedFixRequest, ctx: ToolContext) -> TaskView:
    """Record a fix that failed, with the hypothesis it tested. Use when a verification still fails
    after an attempted fix, before trying the next one. Refused once the task's three attempts
    are spent.
    """
    async with open_tool_state(ctx) as state:
        return record_failed_fix(create_task_work(state), request)


TASK_TOOLS = (
    ToolSpec(
        name='task_declare',
        title='Declare the plan tasks',
        annotations=REFRESHES,
        icon='task',
        request_model=TaskDeclareRequest,
        result_model=TaskView,
        handler=task_declare,
    ),
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
        result_model=VerifyView,
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
