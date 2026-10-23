"""The errors of the workspace paths."""

from mightymodels_core.primitives import StateError


class OutsideStateDirectoryError(StateError):
    def __init__(self, *, shown: str, state_directory: str) -> None:
        self.shown = shown
        self.state_directory = state_directory
        super().__init__(
            f'{shown} resolves outside {state_directory}/ and is not read or written; '
            'remove the symlink that leads there'
        )


class TicketFileSyntaxError(StateError):
    def __init__(self, *, line: int | None, reason: str) -> None:
        self.line = line
        self.reason = reason
        where = 'ticket.yml' if line is None else f'ticket.yml:{line}'
        super().__init__(f'{where}: {reason}')


class TicketFileTypeError(StateError):
    def __init__(self, *, key_path: str, line: int | None, reason: str) -> None:
        self.key_path = key_path
        self.line = line
        self.reason = reason
        where = 'ticket.yml' if line is None else f'ticket.yml:{line}'
        super().__init__(f'{where}: {key_path}: {reason}')


class LoneSurrogateError(StateError):
    def __init__(self, *, character: str) -> None:
        self.character = character
        super().__init__(
            f'U+{ord(character):04X} is a lone surrogate and cannot be written to ticket.yml'
        )


type TicketFileIssue = TicketFileSyntaxError | TicketFileTypeError
