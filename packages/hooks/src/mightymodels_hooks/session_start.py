"""The `session-start` hook: export the plugin data directory, then prune old session pointers.

A command run through the Bash tool has none of the plugin's variables, so the hook appends one
line to the session's env file, the export of the data directory, unless the file already holds
that line. A last line that has no newline is read as a whole line: when it is the export the file
is left as it is, and when it is anything else the hook ends it with a newline first, so the
export starts a line of its own. The file is read and written with no newline translation and the
export is looked for as the text the hook writes, where a line starts. When the plugin data
variable or the env file is missing the hook says so on standard error and stops with exit 0.

The export is written before the database opens. Pruning pointers older than the retention is
housekeeping, so a database that cannot be opened is noted on standard error and the hook still
exits 0.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from mightymodels_core.database import DatabaseError
from mightymodels_core.edge import (
    PLUGIN_DATA_VARIABLE,
    DataDirectoryMissingError,
    data_directory_from,
    export_line,
    open_state,
)
from mightymodels_core.primitives import StateError
from mightymodels_core.session_pointers import SqliteSessionPointerRepository
from mightymodels_core.units_of_work import write_entry
from mightymodels_core.workspace import find_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.primitives import Clock

    from mightymodels_hooks.cli import HookPayload

ENV_FILE_VARIABLE = 'CLAUDE_ENV_FILE'


class EnvFileMissingError(StateError):
    def __init__(self) -> None:
        super().__init__(
            f'{ENV_FILE_VARIABLE} is not set, so there is no session env file to export the '
            'plugin data directory to; Claude Code sets it for a SessionStart hook'
        )


def append_export(env_file: Path, line: str) -> None:
    held = env_file.read_text(encoding='utf-8', newline='') if env_file.is_file() else ''
    missing_newline = '\n' if held and not held.endswith('\n') else ''
    whole_lines = f'{held}{missing_newline}'
    if whole_lines.startswith(line) or f'\n{line}' in whole_lines:
        return

    with env_file.open('a', encoding='utf-8', newline='') as file:
        file.write(f'{missing_newline}{line}')


def export_data_directory(environ: Mapping[str, str]) -> Path | StateError:
    data_directory = data_directory_from(environ, PLUGIN_DATA_VARIABLE)
    if isinstance(data_directory, DataDirectoryMissingError):
        return data_directory

    env_file = environ.get(ENV_FILE_VARIABLE, '')
    if not env_file:
        return EnvFileMissingError()

    append_export(Path(env_file), export_line(data_directory))
    return data_directory


def start_directory(payload: HookPayload) -> Path:
    cwd = payload.get('cwd')
    return Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionStartHandler:
    environ: Mapping[str, str]
    stderr: TextIO
    clock: Clock

    def note(self, error: Exception) -> None:
        self.stderr.write(f'mightymodels-hooks: session-start: {error}\n')

    async def prune_pointers(self, data_directory: Path, start: Path) -> int:
        async with open_state(data_directory, start) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                pointers = SqliteSessionPointerRepository(
                    unit=entry.unit, repository_id=entry.repository_id, clock=self.clock
                )
                return pointers.prune()

    async def handle(self, payload: HookPayload) -> str | None:
        exported = export_data_directory(self.environ)
        if isinstance(exported, StateError):
            self.note(exported)
            return None

        start = find_root(self.environ, start_directory(payload))
        try:
            await self.prune_pointers(exported, start)
        except (StateError, DatabaseError, OSError) as error:
            self.note(error)

        return None
