"""The seams the server reaches core through, and the frozen container its lifespan yields."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from mightymodels_core.edge import OpenState


@runtime_checkable
class StateOpener(Protocol):
    def open(self) -> AbstractAsyncContextManager[OpenState]: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class ServerDependencies:
    state: StateOpener
