"""The python-harness MCP server: versioned Python documentation search and reading over stdio."""

from collections.abc import AsyncGenerator, Generator
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass

import anyio
import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from python_harness.documentation.domain import PythonVersion
from python_harness.documentation.errors import DocumentationError
from python_harness.documentation.repository import documentation_http_client
from python_harness.documentation.services import (
    DocumentationService,
    build_documentation_service,
    call_deadline,
)
from python_harness.documentation.settings import Settings
from python_harness.tools.read_python_docs import use_case as read_use_case
from python_harness.tools.read_python_docs.schema import (
    DEFAULT_PAGE_CHARACTERS,
    PageCharacters,
    PageOffset,
    ReadRequest,
    SymbolName,
)
from python_harness.tools.search_python_docs import use_case as search_use_case
from python_harness.tools.search_python_docs.schema import (
    DEFAULT_SEARCH_LIMIT,
    SearchLimit,
    SearchRequest,
    SearchResult,
    SymbolQuery,
)

SERVER_NAME = 'python-harness'
SERVER_INSTRUCTIONS = (
    'Official Python standard-library documentation for a specific Python version.'
    ' Find exact names with search_python_docs, then read them with read_python_docs.'
)
READ_ONLY_REMOTE = ToolAnnotations(read_only_hint=True, open_world_hint=True)


@contextmanager
def tool_errors() -> Generator[None]:
    try:
        yield
    except DocumentationError as error:
        raise ToolError(str(error)) from error


async def close_client(client: httpx.AsyncClient, timeout_seconds: float) -> None:
    with anyio.move_on_after(timeout_seconds, shield=True):
        await client.aclose()


@asynccontextmanager
async def documentation_service(
    settings: Settings, http_transport: httpx.AsyncBaseTransport | None = None
) -> AsyncGenerator[DocumentationService]:
    async with AsyncExitStack() as stack:
        client = documentation_http_client(settings, http_transport)
        stack.push_async_callback(close_client, client, settings.shutdown_timeout_seconds)
        fills = await stack.enter_async_context(anyio.create_task_group())
        stack.callback(fills.cancel_scope.cancel)
        yield build_documentation_service(settings, client, fills)


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentationTools:
    service: DocumentationService

    async def search_python_docs(
        self,
        *,
        version: PythonVersion,
        query: SymbolQuery,
        limit: SearchLimit = DEFAULT_SEARCH_LIMIT,
    ) -> SearchResult:
        """Find official Python standard-library symbols by name for one Python version.

        Each match is labeled exact, prefix, or approximate; treat approximate matches
        as guesses and confirm them before relying on them.
        """
        service = self.service
        request = SearchRequest(version=version, query=query, limit=limit)
        with tool_errors(), call_deadline(service.settings.call_timeout_seconds):
            return await search_use_case.run(service, request)

    async def read_python_docs(
        self,
        *,
        version: PythonVersion,
        symbol: SymbolName,
        offset: PageOffset = 0,
        max_chars: PageCharacters = DEFAULT_PAGE_CHARACTERS,
    ) -> str:
        """Read one symbol's official documentation as Markdown, one page at a time.

        The first line names the symbol, its kind, the documentation version, and the
        source URL; the last line gives the next offset or marks the end of the section.
        """
        service = self.service
        request = ReadRequest(version=version, symbol=symbol, offset=offset, max_chars=max_chars)
        with tool_errors(), call_deadline(service.settings.call_timeout_seconds):
            return await read_use_case.run(service, request)


def build_server(service: DocumentationService) -> MCPServer:
    documentation = DocumentationTools(service=service)
    server = MCPServer(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    server.add_tool(documentation.search_python_docs, annotations=READ_ONLY_REMOTE)
    server.add_tool(
        documentation.read_python_docs, annotations=READ_ONLY_REMOTE, structured_output=False
    )
    return server


async def serve(settings: Settings) -> None:
    async with documentation_service(settings) as service:
        await build_server(service).run_stdio_async()


def main() -> int:
    anyio.run(serve, Settings())
    return 0
