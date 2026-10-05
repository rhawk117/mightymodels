"""Bounded HTTP retrieval of official pages and inventories, with failures translated."""

from dataclasses import dataclass

import anyio
import httpx

from python_harness.documentation.domain import DocumentationUrl, PythonVersion
from python_harness.documentation.errors import (
    DocumentationError,
    DownloadTooLargeError,
    PageNotFoundError,
    RetrievalFailedError,
    UpstreamStatusError,
    VersionNotPublishedError,
)
from python_harness.documentation.extraction import extract_markdown
from python_harness.documentation.inventory import parse_inventory
from python_harness.documentation.matching import SymbolCatalog, catalog_symbols
from python_harness.documentation.settings import Settings
from python_harness.documentation.store import CachedLoader


def documentation_http_client(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(
            settings.request_timeout_seconds,
            connect=settings.connect_timeout_seconds,
            pool=settings.pool_timeout_seconds,
        ),
        limits=httpx.Limits(
            max_connections=settings.http_max_connections,
            max_keepalive_connections=settings.http_max_keepalive_connections,
            keepalive_expiry=settings.http_keepalive_expiry_seconds,
        ),
    )


def inventory_url(version: PythonVersion) -> DocumentationUrl:
    return DocumentationUrl.model_validate(f'{version.base_url}objects.inv')


def response_failure(response: httpx.Response) -> DocumentationError | None:
    if response.status_code == httpx.codes.NOT_FOUND:
        return PageNotFoundError(str(response.url))
    if not response.is_success:
        return UpstreamStatusError(response.status_code)
    return None


async def bounded_body(response: httpx.Response, settings: Settings) -> bytes:
    content = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=settings.download_chunk_bytes):
        if len(content) + len(chunk) > settings.download_max_bytes:
            raise DownloadTooLargeError(settings.download_max_bytes)
        content.extend(chunk)
    return bytes(content)


def build_catalog(content: bytes, version: PythonVersion, settings: Settings) -> SymbolCatalog:
    return catalog_symbols(parse_inventory(content, version, settings))


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class DocumentationSource:
    client: httpx.AsyncClient
    downloads: anyio.CapacityLimiter
    parsers: anyio.CapacityLimiter
    settings: Settings

    async def fetch(self, url: DocumentationUrl) -> bytes:
        try:
            return await self.download(url)
        except httpx.RequestError as error:
            raise RetrievalFailedError(url.root) from error

    async def download(self, url: DocumentationUrl) -> bytes:
        async with (
            self.downloads,
            self.client.stream('GET', url.root, follow_redirects=False) as response,
        ):
            if (failure := response_failure(response)) is not None:
                raise failure
            return await bounded_body(response, self.settings)

    async def catalog(self, version: PythonVersion) -> SymbolCatalog:
        try:
            content = await self.fetch(inventory_url(version))
        except PageNotFoundError as error:
            raise VersionNotPublishedError(version.root) from error
        return await anyio.to_thread.run_sync(
            build_catalog, content, version, self.settings, limiter=self.parsers
        )


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class SectionLoader:
    pages: CachedLoader[DocumentationUrl, bytes]
    parsers: anyio.CapacityLimiter

    async def __call__(self, url: DocumentationUrl) -> str:
        content = await self.pages.get(url.page_url)
        return await anyio.to_thread.run_sync(extract_markdown, content, url, limiter=self.parsers)
