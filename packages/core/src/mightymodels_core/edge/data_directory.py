"""The plugin data directory, where the state database is kept, and how each edge learns it.

Claude Code sets `PLUGIN_DATA_VARIABLE` for the plugin's MCP server and for its hook commands, and
for nothing started through the Bash tool. So the SessionStart hook writes the directory into the
session's env file under `SESSION_DATA_VARIABLE`, a name of this plugin's own. The env file is
shared by every plugin, and a second plugin exporting `PLUGIN_DATA_VARIABLE` there would otherwise
point the command at its directory.

Each edge reads exactly one of the two and there is no fallback from one to the other. An unset or
empty variable is the absence the edge refuses on, naming the variable.
"""

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import DataDirectoryMissingError

if TYPE_CHECKING:
    from collections.abc import Mapping

PLUGIN_DATA_VARIABLE = 'CLAUDE_PLUGIN_DATA'
SESSION_DATA_VARIABLE = 'MIGHTYMODELS_DATA_DIR'

type DataDirectory = Path | DataDirectoryMissingError


def data_directory_from(environ: Mapping[str, str], variable: str) -> DataDirectory:
    directory = environ.get(variable, '')
    if not directory:
        return DataDirectoryMissingError(variable=variable, session_variable=SESSION_DATA_VARIABLE)

    return Path(directory)


def export_line(data_directory: Path) -> str:
    return f'export {SESSION_DATA_VARIABLE}={shlex.quote(str(data_directory))}\n'
