"""The contract tools: thin async handlers over the sync use cases, and their registration.

contract_approve asks one form, listing every command with its argv, when some command leaves its
approver blank; the user approves the list or declines it. contract_retire asks its own form
under the same condition. A declined or cancelled form returns the needs-input text as a normal
result. contract_approve and contract_status ask git only for HEAD, and contract_retire asks it
nothing. The resolver's annotations are read at runtime, so `RoundAsk` is a module-level plain
assignment and `ContractApproveRequest` a runtime import.

contract_run runs the approved commands without a form, because the approved contract is the
permission. Only the primary may call it, as it may call contract_approve and contract_retire;
the main-thread hook denies all three to a subagent. When that hook cannot run, its shell wrapper
refuses a subagent's contract_run only, so a subagent's contract_approve or contract_retire goes
through. Its progress goes out as notifications whose position rises on every one, since a
heartbeat repeats a command's position.
"""

import itertools
import os
from contextlib import suppress
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import anyio
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mightymodels_core.contract.runs import (
    ContractRunner,
    RunRequest,
    child_environment,
)
from mightymodels_core.edge import create_clock
from mightymodels_core.process import get_process_runner
from mightymodels_core.units_of_work import TaskWork
from pydantic import BaseModel

from mightymodels_mcp.forms.choices import Choice, ChoiceQuestion, ChoiceRound, answers_of
from mightymodels_mcp.forms.needs_input import needs_input_text
from mightymodels_mcp.server.annotations import READS, WRITES
from mightymodels_mcp.server.registration import ToolSpec, open_tool_state, register_specs
from mightymodels_mcp.server.requests import USER_APPROVER
from mightymodels_mcp.server.state import create_work

from .schemas import (
    ContractApproveRequest,
    ContractRequest,
    ContractRetireRequest,
    ContractRunRequest,
    create_approved_commands,
    create_retire_request,
    leaves_approver_blank,
)
from .use_cases import (
    ContractApproval,
    approve_contract,
    retire_contract,
    show_contract_run,
    show_contract_status,
)
from .views import (
    ContractRunView,
    ContractView,
    render_approval_declined,
    render_retirement_declined,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mightymodels_core.contract.runs import RunProgress

    from mightymodels_mcp.forms.choices import ChoiceOutcome
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext

APPROVE_MESSAGE = 'Approve these verification commands?'
APPROVAL_ARGUMENT = 'approval'
APPROVE = 'approve'
DECLINE = 'decline'
PASS_APPROVER = f'approved_by "{USER_APPROVER}" on each command, once the user approved'


RETIRE_MESSAGE = 'Retire this verification command?'
PASS_RETIRE_APPROVER = f'approved_by "{USER_APPROVER}", once the user approved'


RoundAsk = Elicit[BaseModel] | BaseModel


def describe_commands(request: ContractApproveRequest) -> str:
    return ''.join(f'\n{command.id}: {" ".join(command.argv)}' for command in request.commands)


def approve_or_decline_question(title: str, description: str) -> ChoiceQuestion:
    return ChoiceQuestion(
        argument=APPROVAL_ARGUMENT,
        title=title,
        description=description,
        choices=(Choice(value=APPROVE, title='Approve'), Choice(value=DECLINE, title='Decline')),
    )


def create_approval_question(request: ContractApproveRequest) -> ChoiceQuestion:
    return approve_or_decline_question(
        f'{APPROVE_MESSAGE}{describe_commands(request)}',
        'Approve every command listed, or decline to revise them.',
    )


def create_approval_round(request: ContractApproveRequest) -> ChoiceRound:
    asked = (create_approval_question(request),) if leaves_approver_blank(request) else ()
    return ChoiceRound(message=APPROVE_MESSAGE, questions=asked)


def create_retire_question(request: ContractRetireRequest) -> ChoiceQuestion:
    return approve_or_decline_question(
        f'{RETIRE_MESSAGE}\n{request.id}: {request.why}',
        'Approve retiring the command, or decline to keep it.',
    )


def ask_retirement(request: ContractRetireRequest) -> RoundAsk:
    asked = () if request.approved_by.strip() else (create_retire_question(request),)
    return ChoiceRound(message=RETIRE_MESSAGE, questions=asked).ask()


def describe_unanswered_retirement(request: ContractRetireRequest) -> str:
    question = replace(create_retire_question(request), prompt=PASS_RETIRE_APPROVER)
    return needs_input_text([question])


def ask_approval(request: ContractApproveRequest) -> RoundAsk:
    return create_approval_round(request).ask()


APPROVAL_RESOLVER = Resolve(ask_approval)
RETIREMENT_RESOLVER = Resolve(ask_retirement)


def describe_unanswered(request: ContractApproveRequest) -> str:
    question = replace(create_approval_question(request), prompt=PASS_APPROVER)
    return needs_input_text([question])


async def contract_approve(
    request: ContractApproveRequest, ctx: ToolContext, *, answers: ChoiceOutcome
) -> ContractView:
    """Approve verification commands for a ticket. Use when the plan fixes the commands that prove
    each acceptance criterion, before work starts. Asks the user when the approver is blank.
    Refused for ids already approved.
    """
    form = answers_of(answers)
    if form is None:
        return ContractView(text=describe_unanswered(request), passing=False)

    if form.get(APPROVAL_ARGUMENT) == DECLINE:
        return render_approval_declined()

    commands = create_approved_commands(request, USER_APPROVER)
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        approval = ContractApproval(slug=request.slug, commands=commands, head=head)
        return approve_contract(create_work(state, TaskWork), approval)


async def contract_retire(
    request: ContractRetireRequest, ctx: ToolContext, *, answers: ChoiceOutcome
) -> ContractView:
    """Retire a contract command that no longer applies. Use when a command is obsolete; to replace
    one, approve a new id with contract_approve, then retire the old one. Asks the user when the
    approver is blank.
    """
    named = bool(request.approved_by.strip())
    form = answers_of(answers)
    if form is None and not named:
        return ContractView(text=describe_unanswered_retirement(request), passing=False)

    if form is not None and form.get(APPROVAL_ARGUMENT) == DECLINE:
        return render_retirement_declined()

    async with open_tool_state(ctx) as state:
        return retire_contract(
            create_work(state, TaskWork), request.slug, create_retire_request(request)
        )


@runtime_checkable
class ProgressSender(Protocol):
    async def report_progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class ToolProgressReporter:
    ctx: ProgressSender
    ticks: Iterator[int] = field(default_factory=itertools.count)

    async def report(self, progress: RunProgress) -> None:
        status = progress.outcome or progress.state
        place = f'{progress.position} of {progress.total}'
        message = f'{progress.key} {status} ({place})'
        with suppress(anyio.BrokenResourceError, anyio.ClosedResourceError):
            await self.ctx.report_progress(next(self.ticks), message=message)


async def contract_run(request: ContractRunRequest, ctx: ToolContext) -> ContractRunView:
    """Run the approved contract commands of a ticket and record a receipt for each. Use when the
    work is done and the commands must prove it. Blocks until the last command ends. Leave ids out
    to run every live command. A failed command does not stop the run. Refused while tracked files
    have changes.
    """
    async with open_tool_state(ctx) as state:
        work = create_work(state, TaskWork)
        runner = ContractRunner(
            work=work,
            processes=get_process_runner(),
            git=state.git,
            clock=create_clock(),
            root=state.checkout.toplevel,
            environment=child_environment(os.environ),
            reporter=ToolProgressReporter(ctx=ctx),
        )
        run = RunRequest(slug=request.slug, asked=request.ids, phase=request.phase)
        result = await runner.run(run)
        return show_contract_run(result)


async def contract_status(request: ContractRequest, ctx: ToolContext) -> ContractView:
    """Show each approved command of a ticket with its latest receipt against the current HEAD. Use
    to see which verifications still need a run. For task readiness overall, use task_ready.
    """
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        return show_contract_status(create_work(state, TaskWork), request.slug, head)


CONTRACT_TOOLS = (
    ToolSpec(
        name='contract_approve',
        title='Approve the contract commands',
        annotations=WRITES,
        icon='contract',
        request_model=ContractApproveRequest,
        result_model=ContractView,
        handler=contract_approve,
        resolvers={'answers': APPROVAL_RESOLVER},
    ),
    ToolSpec(
        name='contract_status',
        title='Show the contract status',
        annotations=READS,
        icon='contract',
        request_model=ContractRequest,
        result_model=ContractView,
        handler=contract_status,
    ),
    ToolSpec(
        name='contract_retire',
        title='Retire a contract command',
        annotations=WRITES,
        icon='contract',
        request_model=ContractRetireRequest,
        result_model=ContractView,
        handler=contract_retire,
        resolvers={'answers': RETIREMENT_RESOLVER},
    ),
    ToolSpec(
        name='contract_run',
        title='Run the contract commands',
        annotations=WRITES,
        icon='contract',
        request_model=ContractRunRequest,
        result_model=ContractRunView,
        handler=contract_run,
    ),
)


def register_contract_tools(catalog: ToolCatalog) -> ToolCatalog:
    return register_specs(catalog, CONTRACT_TOOLS)
