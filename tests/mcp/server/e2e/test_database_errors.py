import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mcp.types import TextContent, ToolAnnotations
from mightymodels_core.database.errors import BusyError, NestedUnitError, SchemaVersionError
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.call_log import CALL_LOGGER_NAME
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolCatalog, ToolDefinition
from mightymodels_mcp.server.requests import RequestModel
from pydantic import BaseModel

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from _pytest.mark import ParameterSet
    from mcp.types import CallToolResult
    from mightymodels_core.database.errors import DatabaseError
    from mightymodels_core.edge import OpenState
    from mightymodels_mcp.server.registration import ToolContext


class ProbeRequest(RequestModel):
    slug: str


class ProbeView(BaseModel):
    slug: str


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedState:
    failure: DatabaseError

    async def __aenter__(self) -> OpenState:
        raise self.failure

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class FailingStateOpener:
    failure: DatabaseError

    def open(self) -> AbstractAsyncContextManager[OpenState]:
        return FailedState(failure=self.failure)


async def open_state(request: ProbeRequest, ctx: ToolContext) -> ProbeView:
    """Open the workflow state through the container."""
    async with ctx.request_context.lifespan_context.state.open():
        return ProbeView(slug=request.slug)


def read_text(result: CallToolResult) -> str:
    return ''.join(block.text for block in result.content if isinstance(block, TextContent))


@dataclass(slots=True, kw_only=True, frozen=True)
class FailureCase:
    name: str
    failure: DatabaseError
    outcome: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def failure_cases() -> pytest.MarkDecorator:
    cases = [
        FailureCase(
            name='busy',
            failure=BusyError(statement='insert', detail='database is locked'),
            outcome='refused',
        ),
        FailureCase(
            name='schema-version',
            failure=SchemaVersionError(found=9, expected=2),
            outcome='refused',
        ),
        FailureCase(name='nested-unit', failure=NestedUnitError(), outcome='error'),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestDatabaseErrors:
    arguments = MappingProxyType({'slug': 'probe-ticket'})

    async def call(self, failure: DatabaseError) -> CallToolResult:
        dependencies = ServerDependencies(state=FailingStateOpener(failure=failure))
        definition = ToolDefinition(
            name='probe_open_state',
            title='probe open state',
            annotations=ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
            icon=load_icon('server'),
            request_model=ProbeRequest,
            result_model=ProbeView,
            handler=open_state,
        )
        server = create_server(dependencies, ToolCatalog().register(definition))
        async with Client(server) as client:
            return await client.call_tool('probe_open_state', dict(self.arguments))

    @failure_cases()
    async def test_database_failure_reaches_the_agent_as_core_words_it(
        self, case: FailureCase, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO, logger=CALL_LOGGER_NAME)

        result = await self.call(case.failure)

        assert result.is_error
        if case.outcome == 'refused':
            assert read_text(result) == f'Error executing tool probe_open_state: {case.failure}'
        else:
            assert read_text(result) == 'Error executing tool probe_open_state'
        (record,) = [r for r in caplog.records if r.name == CALL_LOGGER_NAME]
        assert record.__dict__['outcome'] == case.outcome
