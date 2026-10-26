"""The contract tools: thin async handlers over the sync use cases, and their registration.

contract_approve asks one form, listing every command with its argv, when some command leaves its
approver blank; the user approves the list or declines it. A declined or cancelled form returns
the needs-input text as a normal result. Both tools ask git only for HEAD. The resolver's
annotations are read at runtime, so `RoundAsk` is a module-level plain assignment and
`ContractApproveRequest` a runtime import.
"""

from dataclasses import replace
from typing import TYPE_CHECKING

from mcp.server.mcpserver.resolve import Elicit, Resolve
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
    create_approved_commands,
    leaves_approver_blank,
)
from .use_cases import (
    ContractApproval,
    approve_contract,
    show_contract_status,
)
from .views import ContractView, render_declined

if TYPE_CHECKING:
    from mightymodels_mcp.forms.choices import ChoiceOutcome
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext

APPROVE_MESSAGE = 'Approve these verification commands?'
APPROVAL_ARGUMENT = 'approval'
APPROVE = 'approve'
DECLINE = 'decline'
PASS_APPROVER = f'approved_by "{USER_APPROVER}" on each command, once the user approved'


RoundAsk = Elicit[BaseModel] | BaseModel


def describe_commands(request: ContractApproveRequest) -> str:
    return ''.join(f'\n{command.id}: {" ".join(command.argv)}' for command in request.commands)


def create_approval_question(request: ContractApproveRequest) -> ChoiceQuestion:
    return ChoiceQuestion(
        argument=APPROVAL_ARGUMENT,
        title=f'{APPROVE_MESSAGE}{describe_commands(request)}',
        description='Approve every command listed, or decline to revise them.',
        choices=(Choice(value=APPROVE, title='Approve'), Choice(value=DECLINE, title='Decline')),
    )


def create_approval_round(request: ContractApproveRequest) -> ChoiceRound:
    asked = (create_approval_question(request),) if leaves_approver_blank(request) else ()
    return ChoiceRound(message=f'{APPROVE_MESSAGE}{describe_commands(request)}', questions=asked)


def ask_approval(request: ContractApproveRequest) -> RoundAsk:
    return create_approval_round(request).ask()


APPROVAL_RESOLVER = Resolve(ask_approval)


def describe_unanswered(request: ContractApproveRequest) -> str:
    question = replace(create_approval_question(request), prompt=PASS_APPROVER)
    return needs_input_text([question])


async def contract_approve(
    request: ContractApproveRequest, ctx: ToolContext, *, answers: ChoiceOutcome
) -> ContractView:
    """Approve verification commands for a ticket; asks the user once when an approver is blank."""
    form = answers_of(answers)
    if form is None:
        return ContractView(text=describe_unanswered(request), passing=False)

    if form.get(APPROVAL_ARGUMENT) == DECLINE:
        return render_declined(DECLINE)

    commands = create_approved_commands(request, USER_APPROVER)
    async with open_tool_state(ctx) as state:
        head = await state.git.resolve_head()
        approval = ContractApproval(slug=request.slug, commands=commands, head=head)
        return approve_contract(create_work(state, TaskWork), approval)


async def contract_status(request: ContractRequest, ctx: ToolContext) -> ContractView:
    """Show each approved command of a ticket with its latest receipt against the current HEAD."""
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
)


def register_contract_tools(catalog: ToolCatalog) -> ToolCatalog:
    return register_specs(catalog, CONTRACT_TOOLS)
