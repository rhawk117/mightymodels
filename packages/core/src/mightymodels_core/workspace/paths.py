"""The names under `.mightymodels/` and the one function that hands out a path below it.

Every path under the state directory comes whole from `contained_in`, which resolves it and
refuses one that leaves the resolved state directory, so a symlink planted below it carries no
read and no write outside.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from .errors import OutsideStateDirectoryError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.primitives import RunId, Slug

PROJECT_DIR_VARIABLE = 'CLAUDE_PROJECT_DIR'
STATE_DIRECTORY = '.mightymodels'
RUNTIME_DIRECTORY = '.runtime'
TICKET_FILE = 'ticket.yml'
TICKET_DRAFT = f'{TICKET_FILE}.tmp'


def find_root(environ: Mapping[str, str], cwd: Path) -> Path:
    project_dir = environ.get(PROJECT_DIR_VARIABLE, '')
    return Path(project_dir) if project_dir else cwd


def contained_in(state_directory: Path, *parts: str) -> Path:
    resolved = state_directory.joinpath(*parts).resolve()
    if not resolved.is_relative_to(state_directory):
        raise OutsideStateDirectoryError(
            shown=str(Path(STATE_DIRECTORY, *parts)), state_directory=STATE_DIRECTORY
        )
    return resolved


def review_parts(slug: Slug | None, run: RunId) -> tuple[str, ...]:
    if slug is None:
        return RUNTIME_DIRECTORY, 'reviews', run
    return slug, 'review', run
