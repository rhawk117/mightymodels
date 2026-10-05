"""Read-through caches whose fills belong to the server, not to the first caller."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import anyio
from anyio.abc import TaskGroup
from cachetools import TTLCache

from python_harness.documentation.errors import (
    FillInterruptedError,
    FillTimeoutError,
    PermanentMissError,
)

if TYPE_CHECKING:
    from collections.abc import Hashable


@dataclass(frozen=True, slots=True)
class FillSucceeded[V]:
    value: V


@dataclass(frozen=True, slots=True)
class FillFailed:
    error: Exception


@dataclass(slots=True, kw_only=True, eq=False)
class PendingFill[V]:
    done: anyio.Event = field(default_factory=anyio.Event)
    outcome: FillSucceeded[V] | FillFailed | None = None

    def result(self) -> V:
        match self.outcome:
            case FillSucceeded(value=value):
                return value
            case FillFailed(error=error):
                raise error.with_traceback(None)
            case None:
                raise FillInterruptedError


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class CachedLoader[K: Hashable, V]:
    """Single-event-loop cache; worker threads must not access this instance."""

    values: TTLCache[K, V]
    misses: TTLCache[K, PermanentMissError]
    loader: Callable[[K], Awaitable[V]]
    fills: TaskGroup
    fill_timeout_seconds: float
    pending: dict[K, PendingFill[V]] = field(default_factory=dict)

    async def get(self, key: K) -> V:
        if (value := self.values.get(key)) is not None:
            return value
        if (miss := self.misses.get(key)) is not None:
            raise miss.with_traceback(None)
        pending = self.pending.get(key)
        if pending is None:
            pending = self.start_fill(key)
        await pending.done.wait()
        return pending.result()

    def start_fill(self, key: K) -> PendingFill[V]:
        pending = PendingFill[V]()
        self.pending[key] = pending
        self.fills.start_soon(self.fill, key, pending)
        return pending

    async def fill(self, key: K, pending: PendingFill[V]) -> None:
        try:
            pending.outcome = await self.load_within_deadline(key)
        except Exception as error:  # noqa: BLE001 - every waiter receives the failure through its PendingFill
            pending.outcome = FillFailed(error)
        finally:
            self.settle(key, pending)

    async def load_within_deadline(self, key: K) -> FillSucceeded[V]:
        try:
            with anyio.fail_after(self.fill_timeout_seconds):
                return FillSucceeded(await self.loader(key))
        except TimeoutError as error:
            raise FillTimeoutError(self.fill_timeout_seconds) from error

    def settle(self, key: K, pending: PendingFill[V]) -> None:
        self.pending.pop(key, None)
        self.remember(key, pending.outcome)
        pending.done.set()

    def fits(self, value: V) -> bool:
        return self.values.getsizeof(value) <= self.values.maxsize

    def remember(self, key: K, outcome: FillSucceeded[V] | FillFailed | None) -> None:
        match outcome:
            case FillSucceeded(value=value) if self.fits(value):
                self.values[key] = value
            case FillFailed(error=PermanentMissError() as miss):
                self.misses[key] = miss
