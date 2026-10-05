"""The `contract` tool's service: the commands a ticket may run to prove its work.

Each command is approved by the user before it is recorded, and an approved id never changes
its argv. `verify run` reads its commands from here and nowhere else, and stores a receipt
for every run.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select

from mightymodels_plugin.clock import now
from mightymodels_plugin.db.checkout import Checkout
from mightymodels_plugin.db.tables import CommandRow, ReceiptRow
from mightymodels_plugin.errors import StateError
from mightymodels_plugin.models.contract import (
    CommandState,
    ContractCommand,
    ContractView,
    Outcome,
    Phase,
)
from mightymodels_plugin.models.task import TASK_ID_PATTERN
from mightymodels_plugin.slug import Slug

SHORT_SHA = 12
TASK_ID = re.compile(TASK_ID_PATTERN)


class MissingApprovalError(StateError):
    def __init__(self) -> None:
        super().__init__('approved_by is required: who approved these commands')


class ChangedCommandError(StateError):
    def __init__(self, command_id: str) -> None:
        super().__init__(
            f'{command_id} is already approved with a different argv; give it a new id'
        )
        self.command_id = command_id


class NoContractError(StateError):
    def __init__(self, slug: Slug) -> None:
        super().__init__(f'{slug} has no approved commands; record a contract first')
        self.slug = slug


class UnknownCommandError(StateError):
    def __init__(self, unknown: list[str]) -> None:
        super().__init__(f'not in the contract: {unknown}; approve them with contract first')
        self.unknown = unknown


@dataclass(slots=True, kw_only=True, frozen=True)
class Approval:
    at: str
    head: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Approved:
    id: str
    argv: tuple[str, ...]
    expect_exit: int
    timeout: int


@dataclass(slots=True, kw_only=True, frozen=True)
class Receipt:
    id: str
    argv: tuple[str, ...]
    outcome: Outcome
    exit: int | None
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    digest: str
    head: str | None
    phase: Phase
    at: str


def owning_task(command_id: str) -> str | None:
    task_id, separator, _ = command_id.partition('.')
    return task_id if separator and TASK_ID.match(task_id) else None


def commands_of(checkout: Checkout, slug: Slug) -> list[CommandRow]:
    query = select(CommandRow).where(CommandRow.slug == slug.root).order_by(CommandRow.command_id)
    return list(checkout.session.scalars(query))


def latest_receipts(checkout: Checkout, slug: Slug) -> dict[str, ReceiptRow]:
    query = select(ReceiptRow).where(ReceiptRow.slug == slug.root).order_by(ReceiptRow.id)
    return {receipt.command_id: receipt for receipt in checkout.session.scalars(query)}


def command_row(slug: Slug, command: ContractCommand, approval: Approval) -> CommandRow:
    return CommandRow(
        slug=slug.root,
        command_id=command.id,
        task_id=owning_task(command.id),
        argv=list(command.argv),
        expect_exit=command.expect_exit,
        timeout=command.timeout,
        approved_by=command.approved_by,
        approved_at=approval.at,
        head=approval.head,
    )


def approve(checkout: Checkout, slug: Slug, commands: Sequence[ContractCommand]) -> ContractView:
    if any(not command.approved_by.strip() for command in commands):
        raise MissingApprovalError
    approval = Approval(at=now(), head=checkout.workspace.git.resolve_head())
    argv_by_id = {row.command_id: tuple(row.argv) for row in commands_of(checkout, slug)}
    fresh: list[ContractCommand] = []
    for command in commands:
        if command.id not in argv_by_id:
            argv_by_id[command.id] = command.argv
            fresh.append(command)
        if argv_by_id[command.id] != command.argv:
            raise ChangedCommandError(command.id)
    checkout.session.add_all(command_row(slug, command, approval) for command in fresh)
    text = f'contract: {len(argv_by_id)} commands ({len(fresh)} new)\n'
    return ContractView(text=text, passing=True)


def state_of(command: CommandRow, latest: ReceiptRow | None, head: str | None) -> str:
    if latest is None:
        return 'never-run'
    if latest.head != head:
        return f'stale ({latest.outcome} at {str(latest.head)[:SHORT_SHA]})'
    return f'{latest.outcome} {latest.phase} expect={command.expect_exit}'


def status(checkout: Checkout, slug: Slug) -> ContractView:
    head = checkout.workspace.git.resolve_head()
    latest = latest_receipts(checkout, slug)
    states = tuple(
        CommandState(
            id=command.command_id,
            argv=tuple(command.argv),
            state=state_of(command, latest.get(command.command_id), head),
        )
        for command in commands_of(checkout, slug)
    )
    rows = ''.join(f'{state.id} {state.state}\n' for state in states)
    header = f'HEAD {(head or "unknown")[:SHORT_SHA]}\n'
    return ContractView(
        text=header + (rows or 'no matching commands\n'),
        passing=all(state.state.split(' ', 1)[0] == Outcome.PASSED for state in states),
        commands=states,
    )


def approved(checkout: Checkout, slug: Slug, ids: Sequence[str] | None) -> list[Approved]:
    commands = {command.command_id: command for command in commands_of(checkout, slug)}
    if not commands:
        raise NoContractError(slug)
    selected = sorted(commands) if ids is None else list(ids)
    unknown = [command_id for command_id in selected if command_id not in commands]
    if unknown:
        raise UnknownCommandError(unknown)
    return [
        Approved(
            id=command_id,
            argv=tuple(commands[command_id].argv),
            expect_exit=commands[command_id].expect_exit,
            timeout=commands[command_id].timeout,
        )
        for command_id in selected
    ]


def record(checkout: Checkout, slug: Slug, receipts: Iterable[Receipt]) -> None:
    checkout.session.add_all(
        ReceiptRow(
            slug=slug.root,
            command_id=receipt.id,
            argv=list(receipt.argv),
            outcome=receipt.outcome,
            exit=receipt.exit,
            duration_ms=receipt.duration_ms,
            stdout_tail=receipt.stdout_tail,
            stderr_tail=receipt.stderr_tail,
            digest=receipt.digest,
            head=receipt.head,
            phase=receipt.phase,
            at=receipt.at,
        )
        for receipt in receipts
    )
