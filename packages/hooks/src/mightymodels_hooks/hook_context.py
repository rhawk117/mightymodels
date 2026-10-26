"""Where a hook runs: the environment, the working directory and the ticket directories near it."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, data_directory_from
from mightymodels_core.primitives.value_types import ARCHIVES_DIRECTORY
from mightymodels_core.workspace import STATE_DIRECTORY, find_root

from mightymodels_hooks.session_start import start_directory

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mightymodels_core.edge import DataDirectory

    from mightymodels_hooks.cli import HookPayload

NUL = '\0'


def ticket_directories(state_directory: Path) -> list[Path]:
    if not state_directory.is_dir():
        return []

    return [
        entry
        for entry in state_directory.iterdir()
        if entry.is_dir() and entry.name != ARCHIVES_DIRECTORY
    ]


def in_a_ticket_directory(resolved: Path, state_directory: Path) -> bool:
    if not resolved.is_relative_to(state_directory):
        return False

    below = resolved.relative_to(state_directory).parts
    return len(below) > 1 and below[0] != ARCHIVES_DIRECTORY


@dataclass(slots=True, kw_only=True, frozen=True)
class HookContext:
    environ: Mapping[str, str]
    cwd: Path

    def data_directory(self) -> DataDirectory:
        return data_directory_from(self.environ, PLUGIN_DATA_VARIABLE)

    def start(self) -> Path:
        return find_root(self.environ, self.cwd)

    def state_directories(self) -> list[Path]:
        start = self.start()
        return [directory.joinpath(STATE_DIRECTORY) for directory in (start, *start.parents)]

    def has_ticket_directory(self) -> bool:
        return any(map(ticket_directories, self.state_directories()))

    def ticket_directory_holds(self, file_path: str) -> bool:
        if NUL in file_path:
            return False

        resolved = self.cwd.joinpath(file_path).resolve()
        return any(
            in_a_ticket_directory(resolved, state_directory.resolve())
            for state_directory in self.state_directories()
        )


def create_hook_context(environ: Mapping[str, str], payload: HookPayload) -> HookContext:
    return HookContext(environ=environ, cwd=start_directory(payload))
