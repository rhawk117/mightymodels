"""Fills belong to the server: waiters can leave, only permanent misses are remembered."""

from collections.abc import AsyncGenerator

import anyio
import pytest
from anyio.abc import TaskGroup
from cachetools import TTLCache
from python_harness.documentation.errors import (
    FillTimeoutError,
    RetrievalFailedError,
    VersionNotPublishedError,
)
from python_harness.documentation.store import CachedLoader
from python_harness.documentation.tests.support import RecordingLoader


@pytest.mark.anyio
class TestCachedLoader:
    @pytest.fixture
    async def fills(self) -> AsyncGenerator[TaskGroup]:
        async with anyio.create_task_group() as group:
            yield group
            group.cancel_scope.cancel()

    def cached(
        self, loader: RecordingLoader, fills: TaskGroup, value_capacity: int = 64
    ) -> CachedLoader[str, str]:
        return CachedLoader(
            values=TTLCache(maxsize=value_capacity, ttl=60, getsizeof=len),
            misses=TTLCache(maxsize=8, ttl=60),
            loader=loader,
            fills=fills,
            fill_timeout_seconds=0.5,
        )

    async def outcome(self, cache: CachedLoader[str, str]) -> str | Exception:
        try:
            return await cache.get('key')
        except (RetrievalFailedError, VersionNotPublishedError) as error:
            return error

    async def get_twice(self, loader: RecordingLoader, fills: TaskGroup) -> list[str | Exception]:
        cache = self.cached(loader, fills)
        return [await self.outcome(cache), await self.outcome(cache)]

    async def test_concurrent_callers_share_one_fill(self, fills: TaskGroup) -> None:
        loader = RecordingLoader(delay_seconds=0.05)
        cache = self.cached(loader, fills)
        results: list[str] = []

        async def collect() -> None:
            results.append(await cache.get('key'))

        async with anyio.create_task_group() as callers:
            for _ in range(5):
                callers.start_soon(collect)
        assert (results, loader.calls) == (['value:key'] * 5, 1)

    async def test_an_abandoning_caller_does_not_cancel_the_fill(self, fills: TaskGroup) -> None:
        loader = RecordingLoader(delay_seconds=0.1)
        cache = self.cached(loader, fills)
        with anyio.move_on_after(0.01):
            await cache.get('key')
        assert (await cache.get('key'), loader.calls) == ('value:key', 1)

    @pytest.mark.parametrize(
        ('failure', 'expected_calls'),
        [
            pytest.param(VersionNotPublishedError('3.99'), 1, id='permanent-miss-remembered'),
            pytest.param(RetrievalFailedError('https://x'), 2, id='transient-failure-retried'),
        ],
    )
    async def test_only_permanent_misses_are_remembered(
        self, fills: TaskGroup, failure: Exception, expected_calls: int
    ) -> None:
        loader = RecordingLoader(failure=failure)
        outcomes = await self.get_twice(loader, fills)
        assert (outcomes, loader.calls) == ([failure, failure], expected_calls)

    async def test_an_oversized_value_is_served_but_not_cached(self, fills: TaskGroup) -> None:
        loader = RecordingLoader()
        cache = self.cached(loader, fills, value_capacity=4)
        results = [await cache.get('key'), await cache.get('key')]
        assert (results, loader.calls) == (['value:key', 'value:key'], 2)

    async def test_a_fill_stops_at_its_own_deadline(self, fills: TaskGroup) -> None:
        cache = self.cached(RecordingLoader(delay_seconds=5), fills)
        with pytest.raises(FillTimeoutError):
            await cache.get('key')
