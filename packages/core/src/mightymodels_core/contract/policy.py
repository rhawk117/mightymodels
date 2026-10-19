"""Every rule a contract approval or a run request is refused by, and the receipt assessment.

The caller fetches the approved commands and the latest receipts, asks a policy and raises the
verdict it returns. A policy reads no repository and no clock, and HEAD is a value passed in. The
command-shape checks (the id's characters and length, a non-empty argv of strings, the timeout
bounds) run here, so every adapter is held to them.
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from mightymodels_core.contract.errors import (
    ChangedCommandError,
    InvalidArgvError,
    InvalidCommandKeyError,
    InvalidTimeoutError,
    MissingApprovalError,
    NoContractError,
    UnknownCommandError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.contract.records import ApprovedCommand, Receipt, RecordedCommand
    from mightymodels_core.primitives import Slug
    from mightymodels_core.schemas.contract import Outcome

type ReceiptState = Literal['never-run', 'stale', 'at-head']
type CommandShapeIssue = (
    InvalidCommandKeyError | InvalidArgvError | InvalidTimeoutError | MissingApprovalError
)

COMMAND_KEY_PATTERN = re.compile(r'[A-Za-z0-9._-]+')


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractOptions:
    key_limit: int = 255
    timeout_floor: int = 1
    timeout_limit: int = 3600


def is_argv(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or not value:
        return False

    return all(isinstance(argument, str) for argument in value)


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandPolicy:
    command: ApprovedCommand
    options: ContractOptions = field(default_factory=ContractOptions)

    @property
    def has_valid_key(self) -> bool:
        key = self.command.key
        return len(key) <= self.options.key_limit and bool(COMMAND_KEY_PATTERN.fullmatch(key))

    @property
    def has_valid_timeout(self) -> bool:
        return self.options.timeout_floor <= self.command.timeout <= self.options.timeout_limit

    @property
    def is_approved_by_someone(self) -> bool:
        return bool(self.command.approved_by.strip())

    def get_command_problem(self) -> CommandShapeIssue | None:
        key = self.command.key
        if not self.has_valid_key:
            return InvalidCommandKeyError(command_key=key, limit=self.options.key_limit)

        if not is_argv(self.command.argv):
            return InvalidArgvError(command_key=key)

        if not self.has_valid_timeout:
            return InvalidTimeoutError(
                command_key=key, timeout=self.command.timeout, limit=self.options.timeout_limit
            )

        if not self.is_approved_by_someone:
            return MissingApprovalError(command_key=key)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovalPolicy:
    commands: Sequence[ApprovedCommand]
    held: Sequence[RecordedCommand]
    options: ContractOptions = field(default_factory=ContractOptions)

    @property
    def held_argv(self) -> dict[str, tuple[str, ...]]:
        return {command.key: command.argv for command in self.held}

    @property
    def new_commands(self) -> list[ApprovedCommand]:
        held = self.held_argv
        first_of_key: dict[str, ApprovedCommand] = {}
        for command in self.commands:
            first_of_key.setdefault(command.key, command)

        return [command for key, command in first_of_key.items() if key not in held]

    def get_approval_problem(self) -> CommandShapeIssue | ChangedCommandError | None:
        for command in self.commands:
            policy = CommandPolicy(command=command, options=self.options)
            if problem := policy.get_command_problem():
                return problem

        approved = self.held_argv | {command.key: command.argv for command in self.new_commands}
        changed = next((c.key for c in self.commands if approved[c.key] != c.argv), None)
        if changed is None:
            return None

        return ChangedCommandError(command_key=changed)


@dataclass(slots=True, kw_only=True, frozen=True)
class PickPolicy:
    slug: Slug
    held: Sequence[RecordedCommand]
    asked: Sequence[str] | None

    @property
    def held_by_key(self) -> Mapping[str, RecordedCommand]:
        return {command.key: command for command in self.held}

    @property
    def picked_keys(self) -> list[str]:
        if self.asked is None:
            return sorted(self.held_by_key)

        return list(self.asked)

    @property
    def unknown_keys(self) -> list[str]:
        return [key for key in self.picked_keys if key not in self.held_by_key]

    @property
    def picked_commands(self) -> list[RecordedCommand]:
        return [self.held_by_key[key] for key in self.picked_keys]

    def get_pick_problem(self) -> NoContractError | UnknownCommandError | None:
        if not self.held:
            return NoContractError(slug=self.slug)

        if unknown := self.unknown_keys:
            return UnknownCommandError(unknown=unknown)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class ReceiptAssessment:
    receipt: Receipt | None
    head: str | None

    @property
    def state(self) -> ReceiptState:
        if self.receipt is None:
            return 'never-run'

        if self.head is None or self.receipt.head != self.head:
            return 'stale'

        return 'at-head'

    @property
    def outcome_at_head(self) -> Outcome | None:
        if self.receipt is None or self.state != 'at-head':
            return None

        return self.receipt.outcome

    @property
    def is_passing(self) -> bool:
        return self.outcome_at_head == 'pass'
