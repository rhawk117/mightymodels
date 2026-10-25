"""The real state opener: core's `open_state` over one data directory and one start directory."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.edge import open_state

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from pathlib import Path

    from mightymodels_core.edge import OpenState


@dataclass(slots=True, kw_only=True, frozen=True)
class LocalStateOpener:
    data_directory: Path
    start: Path

    def open(self) -> AbstractAsyncContextManager[OpenState]:
        return open_state(self.data_directory, self.start)
