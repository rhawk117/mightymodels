"""What the contract tools return: the rendered text, whether the contract passes, the commands."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import short_head
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from mightymodels_core.contract.policy import ReceiptAssessment
    from mightymodels_core.contract.records import RecordedCommand
    from mightymodels_core.contract.services import ApprovalResult, CommandStatus, ContractStatus


class CommandView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    argv: tuple[str, ...]
    state: str


class ContractView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    passing: bool
    commands: tuple[CommandView, ...] = ()


def render_state(command: RecordedCommand, assessment: ReceiptAssessment) -> str:
    receipt = assessment.receipt
    if receipt is None:
        return 'never-run'

    if assessment.state == 'at-head':
        return f'{receipt.outcome} {receipt.phase} expect={command.expect_exit}'

    return f'stale ({receipt.outcome} at {short_head(receipt.head)})'


def create_command_view(status: CommandStatus) -> CommandView:
    command = status.command
    return CommandView(
        id=command.key, argv=command.argv, state=render_state(command, status.assessment)
    )


def render_approved(result: ApprovalResult) -> ContractView:
    text = f'contract: {result.held} commands ({len(result.new_keys)} new)\n'
    return ContractView(text=text, passing=True)


def render_declined(choice: str) -> ContractView:
    text = f'not approved: the user chose to {choice}; revise the commands, then call again\n'
    return ContractView(text=text, passing=False)


def render_status(status: ContractStatus) -> ContractView:
    views = tuple(map(create_command_view, status.commands))
    rows = ''.join(f'{view.id} {view.state}\n' for view in views) or 'no matching commands\n'
    return ContractView(
        text=f'HEAD {short_head(status.head)}\n{rows}', passing=status.is_passing, commands=views
    )
