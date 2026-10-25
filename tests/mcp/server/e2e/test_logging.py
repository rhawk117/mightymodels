import logging
from dataclasses import dataclass
from io import StringIO
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated

import pytest
from mcp import Client
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.shared.exceptions import MCPError
from mcp.types import ElicitResult, InputRequiredResult, ToolAnnotations
from mightymodels_core.edge import DataDirectoryMissingError
from mightymodels_mcp.server.call_log import (
    CALL_LOGGER_NAME,
    LogSettings,
    installed_logging,
)
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolCatalog, ToolDefinition
from mightymodels_mcp.server.requests import RequestModel
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from _pytest.mark import ParameterSet
    from mcp.client.session import ClientRequestContext
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ElicitRequestParams, InputResponses
    from mightymodels_mcp.server.call_log import (
        LogLevel,
    )
    from mightymodels_mcp.server.dependencies import ServerDependencies
    from mightymodels_mcp.server.registration import ToolContext, ToolHandler

    from tests.mcp.server.server_harness import ServerHarness

DISTINCT_VALUE = 'zx-distinct-payload-7731'
FORM_TOOL = 'probe_form'
REQUEST_STATE_LOGGER = 'mcp.server.request_state'


class ProbeRequest(RequestModel):
    slug: str
    payload: str


class ProbeView(BaseModel):
    slug: str


class Confirmation(BaseModel):
    confirmed: bool


class ConfirmationAsker:
    def ask(self) -> Elicit[Confirmation]:
        return Elicit('Proceed?', Confirmation)


ConfirmationField = Annotated[Confirmation, Resolve(ConfirmationAsker().ask)]


class ConfirmationAcceptor:
    async def accept(
        self, context: ClientRequestContext, params: ElicitRequestParams
    ) -> ElicitResult:
        assert params.message, context
        return ElicitResult(action='accept', content={'confirmed': True})


class ProbeTools:
    async def succeed(self, request: ProbeRequest, _: ToolContext) -> ProbeView:
        """Succeed."""
        return ProbeView(slug=request.slug)

    async def refuse(self, request: ProbeRequest, _: ToolContext) -> ProbeView:
        """Be refused by core."""
        assert request.slug
        raise DataDirectoryMissingError(variable='VARIABLE', session_variable='SESSION')

    async def crash(self, request: ProbeRequest, _: ToolContext) -> ProbeView:
        """Fail the way a bug does."""
        raise RuntimeError(request.slug)

    async def confirm(self, slug: str, confirmation: ConfirmationField) -> str:
        """Ask the client for a confirmation first."""
        return f'{slug} {confirmation.confirmed}'


@dataclass(slots=True, kw_only=True, frozen=True)
class CallOutcomeCase:
    name: str
    outcome: str

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def call_outcome_cases() -> pytest.MarkDecorator:
    cases = [
        CallOutcomeCase(name='probe_succeed', outcome='ok'),
        CallOutcomeCase(name='probe_refuse', outcome='refused'),
        CallOutcomeCase(name='probe_crash', outcome='error'),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


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


def create_probe_catalog() -> ToolCatalog:
    probes = ProbeTools()
    return (
        ToolCatalog()
        .register(create_probe_definition('probe_succeed', probes.succeed))
        .register(create_probe_definition('probe_refuse', probes.refuse))
        .register(create_probe_definition('probe_crash', probes.crash))
    )


def create_form_server(harness: ServerHarness) -> MCPServer[ServerDependencies]:
    server = harness.create_server(create_probe_catalog())
    server.add_tool(ProbeTools().confirm, name=FORM_TOOL)
    return server


@pytest.fixture
def log_level() -> LogLevel:
    return 'INFO'


@pytest.fixture
def stderr() -> StringIO:
    return StringIO()


@pytest.fixture
def logs(
    server_harness: ServerHarness, log_level: LogLevel, stderr: StringIO
) -> Generator[LogSettings]:
    settings = LogSettings(
        level=log_level, data_directory=server_harness.data_directory, stream=stderr
    )
    with installed_logging(settings):
        yield settings


@pytest.mark.usefixtures('logs')
class TestCallLogging:
    arguments = MappingProxyType({'slug': 'probe-ticket', 'payload': DISTINCT_VALUE})

    @pytest.fixture
    async def client(self, server_harness: ServerHarness) -> AsyncGenerator[Client]:
        async with Client(server_harness.create_server(create_probe_catalog())) as client:
            yield client

    def call_records(self, caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
        return [record for record in caplog.records if record.name == CALL_LOGGER_NAME]

    @call_outcome_cases()
    async def test_one_call_writes_one_record(
        self, client: Client, caplog: pytest.LogCaptureFixture, case: CallOutcomeCase
    ) -> None:
        await client.call_tool(case.name, dict(self.arguments))

        (record,) = self.call_records(caplog)
        assert record.__dict__['tool_name'] == case.name
        assert record.__dict__['slug'] == 'probe-ticket'
        assert record.__dict__['outcome'] == case.outcome
        assert record.__dict__['duration_ms'] >= 0

    async def test_record_carries_no_other_argument_value(
        self,
        client: Client,
        caplog: pytest.LogCaptureFixture,
        stderr: StringIO,
        logs: LogSettings,
    ) -> None:
        await client.call_tool('probe_succeed', dict(self.arguments))

        (record,) = self.call_records(caplog)
        assert DISTINCT_VALUE not in str(record.__dict__)
        assert DISTINCT_VALUE not in stderr.getvalue()
        assert DISTINCT_VALUE not in logs.file_path.read_text()

    async def test_record_reaches_stderr_and_the_rotated_file(
        self, client: Client, stderr: StringIO, logs: LogSettings
    ) -> None:
        await client.call_tool('probe_succeed', dict(self.arguments))

        expected = 'tool=probe_succeed slug=probe-ticket outcome=ok'
        assert expected in stderr.getvalue()
        assert expected in logs.file_path.read_text()

    async def test_sdk_records_reach_the_same_handlers(
        self, stderr: StringIO, logs: LogSettings
    ) -> None:
        logging.getLogger('mcp.probe').warning('sdk-probe-record')

        assert 'sdk-probe-record' in stderr.getvalue()
        assert 'sdk-probe-record' in logs.file_path.read_text()


class TestWarningLevel:
    @pytest.fixture
    def log_level(self) -> LogLevel:
        return 'WARNING'

    async def test_level_filters_the_call_record(
        self, server_harness: ServerHarness, logs: LogSettings
    ) -> None:
        arguments = {'slug': 'probe-ticket', 'payload': DISTINCT_VALUE}
        async with Client(server_harness.create_server(create_probe_catalog())) as client:
            await client.call_tool('probe_succeed', arguments)
            await client.call_tool('probe_crash', arguments)

        written = logs.file_path.read_text()
        assert 'tool=probe_succeed' not in written
        assert 'tool=probe_crash' in written


class TestRejectedRequestState:
    arguments = MappingProxyType({'slug': 'probe-ticket'})

    async def start_round(self, server_harness: ServerHarness) -> InputRequiredResult:
        acceptor = ConfirmationAcceptor()
        server = create_form_server(server_harness)
        async with Client(server, elicitation_callback=acceptor.accept) as client:
            first = await client.session.call_tool(
                FORM_TOOL, dict(self.arguments), allow_input_required=True
            )

        assert isinstance(first, InputRequiredResult)
        return first

    async def resume_on_rebuilt_server(
        self, server_harness: ServerHarness, first: InputRequiredResult
    ) -> MCPError:
        acceptor = ConfirmationAcceptor()
        answers: InputResponses = {
            key: ElicitResult(action='accept', content={'confirmed': True})
            for key in first.input_requests or {}
        }
        server = create_form_server(server_harness)
        async with Client(server, elicitation_callback=acceptor.accept) as client:
            with pytest.raises(MCPError) as rejected:
                await client.session.call_tool(
                    FORM_TOOL,
                    dict(self.arguments),
                    input_responses=answers,
                    request_state=first.request_state,
                    allow_input_required=True,
                )

        return rejected.value

    async def test_state_from_another_server_is_rejected_and_logged(
        self, server_harness: ServerHarness, logs: LogSettings
    ) -> None:
        first = await self.start_round(server_harness)

        rejected = await self.resume_on_rebuilt_server(server_harness, first)

        assert rejected.message == 'Invalid or expired requestState'
        assert rejected.data == {'reason': 'invalid_request_state'}
        records = [
            line for line in logs.file_path.read_text().splitlines() if REQUEST_STATE_LOGGER in line
        ]
        assert len(records) == 1
        assert 'requestState rejected on tools/call: unknown key' in records[0]
