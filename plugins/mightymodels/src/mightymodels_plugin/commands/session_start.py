"""The `mightymodels session-start` command, which the plugin's SessionStart hook runs.

A command run through the Bash tool has none of the plugin's variables, so `verify run` could not
find the state database the server opened. The hook has the data directory and the session's env
file, and Claude Code sets what that file exports in every later Bash command of the session, a
subagent's included. The command appends one line there, the export of the data directory, and
does nothing else: it creates no directory, prints nothing and loads no database or server
package.
"""

from collections.abc import Mapping
from pathlib import Path

from mightymodels_plugin.commands.rejection import rejected
from mightymodels_plugin.data_directory import (
    PLUGIN_DATA_VARIABLE,
    DataDirectoryMissingError,
    data_directory_from,
    export_line,
)
from mightymodels_plugin.errors import StateError

ENV_FILE_VARIABLE = 'CLAUDE_ENV_FILE'


class EnvFileMissingError(StateError):
    def __init__(self) -> None:
        super().__init__(
            f'{ENV_FILE_VARIABLE} is not set, so there is no session env file to export the '
            'plugin data directory to; Claude Code sets it for a SessionStart hook'
        )


def export_data_directory(environ: Mapping[str, str]) -> int:
    data_directory = data_directory_from(environ, PLUGIN_DATA_VARIABLE)
    if isinstance(data_directory, DataDirectoryMissingError):
        return rejected(data_directory)
    env_file = environ.get(ENV_FILE_VARIABLE, '')
    if not env_file:
        return rejected(EnvFileMissingError())
    with Path(env_file).open('a', encoding='utf-8') as exports:
        exports.write(export_line(data_directory))
    return 0
