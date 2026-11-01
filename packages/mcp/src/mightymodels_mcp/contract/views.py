"""What the contract tools return: the rendered text, whether the contract passes, the commands."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import short_head
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from mightymodels_core.contract.policy import ReceiptAssessment
    from mightymodels_core.contract.records import Receipt, RecordedCommand, Retirement
    from mightymodels_core.contract.runs import RunResult
    from mightymodels_core.contract.services import (
        ApprovalResult,
        CommandStatus,
        ContractStatus,
        RetireRequest,
    )


class CommandView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    argv: tuple[str, ...]
    state: str


class RetiredView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    by: str
    why: str
    approval_source: str


class ContractView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    passing: bool
    commands: tuple[CommandView, ...] = ()
    retired: tuple[RetiredView, ...] = ()


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


def render_retired(request: RetireRequest) -> ContractView:
    text = f'retired {request.key} ({request.approval_source}, by {request.by}): {request.why}\n'
    return ContractView(text=text, passing=True)


def create_retired_view(key: str, retirement: Retirement) -> RetiredView:
    return RetiredView(
        id=key,
        by=retirement.by,
        why=retirement.why,
        approval_source=retirement.approval_source,
    )


def render_declined(choice: str) -> ContractView:
    text = f'not approved: the user chose to {choice}; revise the commands, then call again\n'
    return ContractView(text=text, passing=False)


def render_status(status: ContractStatus) -> ContractView:
    views = tuple(map(create_command_view, status.commands))
    retired = tuple(
        create_retired_view(command.key, command.retirement) for command in status.retired
    )
    live = ''.join(f'{view.id} {view.state}\n' for view in views)
    gone = ''.join(
        f'{view.id} retired by {view.by} ({view.approval_source}): {view.why}\n' for view in retired
    )
    rows = live + gone or 'no matching commands\n'
    return ContractView(
        text=f'HEAD {short_head(status.head)}\n{rows}',
        passing=status.is_passing,
        commands=views,
        retired=retired,
    )


class RunReceiptView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    outcome: str
    exit: int | None
    duration_ms: int
    head: str | None
    stdout_tail: str
    stderr_tail: str
    approval_source: str


class ContractRunView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    passing: bool
    receipts: tuple[RunReceiptView, ...] = ()


def create_run_receipt_view(receipt: Receipt, approval_source: str) -> RunReceiptView:
    return RunReceiptView(
        id=receipt.key,
        outcome=receipt.outcome,
        exit=receipt.exit,
        duration_ms=receipt.duration_ms,
        head=receipt.head,
        stdout_tail=receipt.stdout_tail,
        stderr_tail=receipt.stderr_tail,
        approval_source=approval_source,
    )


def render_run_line(view: RunReceiptView) -> str:
    return (
        f'{view.id} {view.outcome} exit={view.exit} {view.duration_ms}ms ({view.approval_source})\n'
    )


def render_run(result: RunResult) -> ContractRunView:
    views = tuple(create_run_receipt_view(run.receipt, run.approval_source) for run in result.runs)
    return ContractRunView(
        text=''.join(map(render_run_line, views)), passing=result.is_passing, receipts=views
    )
