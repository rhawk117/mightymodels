"""The contract tools' requests, and the core commands they turn into.

A command's key pattern, argv shape, timeout bounds and approver stay core's to check, so a
request only holds the shapes. An approver the call leaves blank is filled with `USER_APPROVER`
once the user approved the list in the form.
"""

from typing import TYPE_CHECKING

from mightymodels_core.contract.records import ApprovedCommand
from pydantic import Field

from mightymodels_mcp.server.requests import NameText, RequestModel, SlugField

if TYPE_CHECKING:
    from mightymodels_core.vocabulary.contract import ApprovalSource

DEFAULT_TIMEOUT = 300


class CommandRequest(RequestModel):
    id: NameText = Field(
        description='The command key, such as I1 or L1, that a receipt is kept under.'
    )
    argv: tuple[str, ...] = Field(
        description='The command and its arguments, one entry per argument; no shell is used.'
    )
    expect_exit: int = Field(default=0, description='The exit code that counts as a pass.')
    timeout: int = Field(
        default=DEFAULT_TIMEOUT,
        description='Seconds the command may run before it counts as a failure.',
    )
    approved_by: NameText = Field(
        default='', description='Who approved the command; leave it blank and the user is asked.'
    )


class ContractApproveRequest(RequestModel):
    slug: SlugField
    commands: tuple[CommandRequest, ...] = Field(description='The contract commands to approve.')


class ContractRequest(RequestModel):
    slug: SlugField


def leaves_approver_blank(request: ContractApproveRequest) -> bool:
    return any(not command.approved_by.strip() for command in request.commands)


def create_approved_command(
    command: CommandRequest, fallback_approver: str, source: ApprovalSource
) -> ApprovedCommand:
    named = bool(command.approved_by.strip())
    return ApprovedCommand(
        key=command.id,
        argv=command.argv,
        expect_exit=command.expect_exit,
        timeout=command.timeout,
        approved_by=command.approved_by if named else fallback_approver,
        approval_source=source,
    )


def create_approved_commands(
    request: ContractApproveRequest, fallback_approver: str
) -> tuple[ApprovedCommand, ...]:
    source: ApprovalSource = 'form' if leaves_approver_blank(request) else 'fallback'
    return tuple(
        create_approved_command(command, fallback_approver, source) for command in request.commands
    )
