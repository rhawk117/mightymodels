"""The errors of the contract repository and of the contract policy."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import Slug


class DuplicateCommandError(StateError):
    def __init__(self, *, ticket_id: int, command_key: str) -> None:
        self.ticket_id = ticket_id
        self.command_key = command_key
        super().__init__(f'ticket {ticket_id} already holds contract command {command_key!r}')


class UnapprovedCommandError(StateError):
    def __init__(self, *, ticket_id: int, command_key: str) -> None:
        self.ticket_id = ticket_id
        self.command_key = command_key
        super().__init__(
            f'ticket {ticket_id} has not approved contract command {command_key!r}; '
            'approve the command before recording a receipt'
        )


class InvalidCommandKeyError(StateError):
    def __init__(self, *, command_key: str, limit: int) -> None:
        self.command_key = command_key
        self.limit = limit
        super().__init__(
            f'{command_key!r} is not a command id: letters, digits, dots, dashes and underscores '
            f'only, at most {limit} characters'
        )


class InvalidArgvError(StateError):
    def __init__(self, *, command_key: str) -> None:
        self.command_key = command_key
        super().__init__(
            f'{command_key}: argv must be a non-empty list of strings; no shell string'
        )


class InvalidTimeoutError(StateError):
    def __init__(self, *, command_key: str, timeout: int, limit: int) -> None:
        self.command_key = command_key
        self.timeout = timeout
        self.limit = limit
        super().__init__(f'{command_key}: timeout {timeout} is outside 1 to {limit} seconds')


class MissingApprovalError(StateError):
    def __init__(self, *, command_key: str) -> None:
        self.command_key = command_key
        super().__init__(f'{command_key}: approved_by is required: who approved these commands')


class ChangedCommandError(StateError):
    def __init__(self, *, command_key: str) -> None:
        self.command_key = command_key
        super().__init__(
            f'{command_key} is already approved with a different argv; give it a new id'
        )


class NoContractError(StateError):
    def __init__(self, *, slug: Slug) -> None:
        self.slug = slug
        super().__init__(f'{slug} has no approved commands; record a contract first')


class UnknownCommandError(StateError):
    def __init__(self, *, unknown: Sequence[str]) -> None:
        self.unknown = tuple(unknown)
        super().__init__(f'not in the contract: {list(unknown)}; approve them with contract first')
