"""The documentation service the tools use, and the factory that composes it."""

from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
import httpx
from anyio.abc import TaskGroup
from cachetools import TTLCache

from python_harness.documentation.domain import (
    DocumentationUrl,
    PythonVersion,
    Symbol,
)
from python_harness.documentation.errors import CallDeadlineExceededError
from python_harness.documentation.matching import SymbolCatalog
from python_harness.documentation.repository import DocumentationSource, SectionLoader
from python_harness.documentation.settings import Settings
from python_harness.documentation.store import CachedLoader

if TYPE_CHECKING:
    from collections.abc import Hashable


@contextmanager
def call_deadline(seconds: float) -> Generator[None]:
    try:
        with anyio.fail_after(seconds):
            yield
    except TimeoutError as error:
        raise CallDeadlineExceededError(seconds) from error


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class DocumentationService:
    catalogs: CachedLoader[PythonVersion, SymbolCatalog]
    sections: CachedLoader[DocumentationUrl, str]
    settings: Settings

    async def catalog(self, version: PythonVersion) -> SymbolCatalog:
        return await self.catalogs.get(version)

    async def section(self, symbol: Symbol) -> str:
        return await self.sections.get(symbol.source_url)


def cached_loader[K: Hashable, V](
    loader: Callable[[K], Awaitable[V]],
    values: TTLCache[K, V],
    *,
    fills: TaskGroup,
    settings: Settings,
) -> CachedLoader[K, V]:
    return CachedLoader(
        values=values,
        misses=TTLCache(
            maxsize=settings.inventory_cache_versions,
            ttl=settings.missing_version_ttl_seconds,
        ),
        loader=loader,
        fills=fills,
        fill_timeout_seconds=settings.fill_timeout_seconds,
    )


def build_documentation_service(
    settings: Settings, client: httpx.AsyncClient, fills: TaskGroup
) -> DocumentationService:
    parsers = anyio.CapacityLimiter(settings.parse_concurrency)
    source = DocumentationSource(
        client=client,
        downloads=anyio.CapacityLimiter(settings.download_concurrency),
        parsers=parsers,
        settings=settings,
    )
    ttl = settings.cache_ttl_seconds
    pages = cached_loader(
        source.fetch,
        TTLCache(settings.page_cache_bytes, ttl, getsizeof=len),
        fills=fills,
        settings=settings,
    )
    return DocumentationService(
        catalogs=cached_loader(
            source.catalog,
            TTLCache(settings.inventory_cache_versions, ttl),
            fills=fills,
            settings=settings,
        ),
        sections=cached_loader(
            SectionLoader(pages=pages, parsers=parsers),
            TTLCache(settings.section_cache_characters, ttl, getsizeof=len),
            fills=fills,
            settings=settings,
        ),
        settings=settings,
    )
