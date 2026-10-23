"""The refusal the edge adds to the ones git and the database already raise."""

from mightymodels_core.primitives import StateError


class DataDirectoryMissingError(StateError):
    def __init__(self, *, variable: str, session_variable: str) -> None:
        self.variable = variable
        super().__init__(
            f'{variable} is not set, so there is no plugin data directory to keep the state '
            f'database in; Claude Code sets CLAUDE_PLUGIN_DATA for the state server, and the '
            f"plugin's SessionStart hook exports {session_variable} to the commands a "
            'session runs'
        )
