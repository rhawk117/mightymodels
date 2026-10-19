"""The values the contract repository hands out and takes in: frozen, never a database row.

An `ApprovedCommand` is what an approval writes. A `RecordedCommand` is what `verify run`
executes, with the task that owns it. A `Receipt` is the result of one run of a command. The
output tails of a receipt are redacted text, which only `redact` produces, so a secret cannot
reach a receipt by the type alone.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.contract.errors import DuplicateCommandError, UnapprovedCommandError
from mightymodels_core.primitives import InvalidTaskIdError, ReadLimit, parse_task_id

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText, TaskId
    from mightymodels_core.schemas.contract import Outcome, Phase

COMMANDS = ReadLimit(rows=1000, kept='contract commands')


def owning_task(command_key: str) -> TaskId | None:
    task_part, separator, _ = command_key.partition('.')
    if not separator:
        return None

    task_key = parse_task_id(task_part)
    return None if isinstance(task_key, InvalidTaskIdError) else task_key


@dataclass(slots=True, kw_only=True, frozen=True)
class Approval:
    at: datetime
    head: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovedCommand:
    key: str
    argv: tuple[str, ...]
    expect_exit: int
    timeout: int
    approved_by: str


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedCommand:
    key: str
    task_key: TaskId | None
    argv: tuple[str, ...]
    expect_exit: int
    timeout: int


@dataclass(slots=True, kw_only=True, frozen=True)
class Receipt:
    key: str
    argv: tuple[str, ...]
    outcome: Outcome
    exit: int | None
    duration_ms: int
    stdout_tail: RedactedText
    stderr_tail: RedactedText
    digest: str
    head: str | None
    phase: Phase
    at: datetime


def duplicate_command_error(
    ticket_id: int, held_keys: Collection[str], commands: Sequence[ApprovedCommand]
) -> DuplicateCommandError | None:
    seen = set(held_keys)
    for command in commands:
        if command.key in seen:
            return DuplicateCommandError(ticket_id=ticket_id, command_key=command.key)

        seen.add(command.key)
    return None


def unapproved_command_error(
    ticket_id: int, approved_keys: Collection[str], receipts: Sequence[Receipt]
) -> UnapprovedCommandError | None:
    for receipt in receipts:
        if receipt.key not in approved_keys:
            return UnapprovedCommandError(ticket_id=ticket_id, command_key=receipt.key)

    return None
