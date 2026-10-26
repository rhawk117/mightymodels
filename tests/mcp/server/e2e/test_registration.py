from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest
from mcp import Client
from mcp.types import TextContent, ToolAnnotations
from mightymodels_core.edge import DataDirectoryMissingError
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolCatalog, ToolDefinition
from mightymodels_mcp.server.requests import RequestModel
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from contextlib import AbstractAsyncContextManager

    from mcp.types import CallToolResult
    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import StateError
    from mightymodels_mcp.server.registration import ToolContext, ToolHandler


class ProbeDetail(RequestModel):
    note: str


class ProbeRequest(RequestModel):
    slug: str
    detail: ProbeDetail


class ProbeView(BaseModel):
    slug: str
    note: str
    reads_server_container: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedState:
    refusal: StateError

    async def __aenter__(self) -> OpenState:
        raise self.refusal

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusingStateOpener:
    refusal: StateError

    def open(self) -> AbstractAsyncContextManager[OpenState]:
        return RefusedState(refusal=self.refusal)


@dataclass(slots=True, kw_only=True, frozen=True)
class ProbeTools:
    dependencies: ServerDependencies

    async def echo(self, request: ProbeRequest, ctx: ToolContext) -> ProbeView:
        """Echo the request and whether the context carries the server's container."""
        container = ctx.request_context.lifespan_context
        return ProbeView(
            slug=request.slug,
            note=request.detail.note,
            reads_server_container=container is self.dependencies,
        )

    async def open_state(self, request: ProbeRequest, ctx: ToolContext) -> ProbeView:
        """Open the workflow state through the container."""
        async with ctx.request_context.lifespan_context.state.open() as state:
            return ProbeView(
                slug=request.slug, note=type(state).__name__, reads_server_container=True
            )

    async def crash(self, request: ProbeRequest, ctx: ToolContext) -> ProbeView:
        """Fail the way a bug does."""
        container = ctx.request_context.lifespan_context
        message = f'secret {type(container.state).__name__} detail for {request.slug}'
        raise RuntimeError(message)


def create_probe_definition(
    name: str, handler: ToolHandler[ProbeRequest, ProbeView]
) -> ToolDefinition[ProbeRequest, ProbeView]:
    return ToolDefinition(
        name=name,
        title=name.replace('_', ' '),
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        icon=load_icon('server'),
        request_model=ProbeRequest,
        result_model=ProbeView,
        handler=handler,
    )


def read_text(result: CallToolResult) -> str:
    return ''.join(block.text for block in result.content if isinstance(block, TextContent))


class TestProbeRegistration:
    refusal = DataDirectoryMissingError(
        variable='CLAUDE_PLUGIN_DATA', session_variable='MIGHTYMODELS_DATA'
    )
    arguments = MappingProxyType({'slug': 'probe-ticket', 'detail': {'note': 'hello'}})

    @pytest.fixture
    def dependencies(self) -> ServerDependencies:
        return ServerDependencies(state=RefusingStateOpener(refusal=self.refusal))

    @pytest.fixture
    async def client(self, dependencies: ServerDependencies) -> AsyncGenerator[Client]:
        probes = ProbeTools(dependencies=dependencies)
        catalog = (
            ToolCatalog()
            .register(create_probe_definition('probe_echo', probes.echo))
            .register(create_probe_definition('probe_open_state', probes.open_state))
            .register(create_probe_definition('probe_crash', probes.crash))
        )
        async with Client(create_server(dependencies, catalog)) as client:
            yield client

    async def list_input_schema(self, client: Client, name: str) -> dict[str, Any]:
        listed = await client.list_tools()
        return next(tool.input_schema for tool in listed.tools if tool.name == name)

    async def test_input_schema_is_the_flat_request_model(self, client: Client) -> None:
        schema = await self.list_input_schema(client, 'probe_echo')
        assert set(schema['properties']) == {'slug', 'detail'}
        assert schema['required'] == ['slug', 'detail']
        assert schema['additionalProperties'] is False

    async def test_flat_arguments_reach_the_handler(self, client: Client) -> None:
        result = await client.call_tool('probe_echo', dict(self.arguments))
        assert not result.is_error
        assert result.structured_content == {
            'slug': 'probe-ticket',
            'note': 'hello',
            'reads_server_container': True,
        }

    async def test_extra_top_level_argument_is_refused(self, client: Client) -> None:
        result = await client.call_tool('probe_echo', {**self.arguments, 'stray': 1})
        assert result.is_error
        assert 'stray' in read_text(result)

    async def test_extra_nested_argument_is_refused(self, client: Client) -> None:
        detail = {'note': 'hello', 'stray': 1}
        result = await client.call_tool('probe_echo', {**self.arguments, 'detail': detail})
        assert result.is_error
        assert 'detail.stray' in read_text(result)

    async def test_core_refusal_arrives_as_a_tool_error(self, client: Client) -> None:
        result = await client.call_tool('probe_open_state', dict(self.arguments))
        assert result.is_error
        assert read_text(result) == f'Error executing tool probe_open_state: {self.refusal}'

    async def test_unexpected_exception_arrives_as_the_generic_error(self, client: Client) -> None:
        result = await client.call_tool('probe_crash', dict(self.arguments))
        assert result.is_error
        assert read_text(result) == 'Error executing tool probe_crash'
