"""The real state opener: core's `open_state` over one data directory and one start directory."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from mightymodels_core.edge import create_clock, open_state

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from pathlib import Path

    from mightymodels_core.database import Database
    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import Clock, RepositoryKey


class WorkConstructor[W](Protocol):
    def __call__(self, *, database: Database, repository_key: RepositoryKey, clock: Clock) -> W: ...


def create_work[W](state: OpenState, work_type: WorkConstructor[W]) -> W:
    return work_type(
        database=state.database,
        repository_key=state.checkout.repository_key(),
        clock=create_clock(),
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class LocalStateOpener:
    data_directory: Path
    start: Path

    def open(self) -> AbstractAsyncContextManager[OpenState]:
        return open_state(self.data_directory, self.start)
