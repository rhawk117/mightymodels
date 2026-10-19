"""The errors of the contract repository."""

from mightymodels_core.primitives import StateError


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
