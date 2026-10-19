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
