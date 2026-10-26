"""The ticket tools' shared e2e fixtures: a probe ticket, a form answerer and a client harness."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import anyio
from mcp.types import ElicitRequestFormParams, ElicitResult
from mightymodels_mcp.main import create_catalog

from mcp import Client

if TYPE_CHECKING:
    from mcp.client.session import ClientRequestContext
    from mcp.types import CallToolResult, ElicitRequestParams

    from tests.mcp.server.server_harness import ServerHarness

type FormAction = Literal['accept', 'decline', 'cancel']

SLUG = 'probe-ticket'
TICKET_PATH = f'.mightymodels/{SLUG}/ticket.yml'
INTERVIEW = MappingProxyType({
    'slug': SLUG,
    'summary': 'Add the ticket tools',
    'context': ['the first concept package'],
})
ANSWERED = MappingProxyType({**INTERVIEW, 'scope': 'med', 'compaction': True, 'branch': 'main'})


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordingAnswerer:
    answers: dict[str, str]
    action: FormAction = 'accept'
    asked: list[frozenset[str]] = field(default_factory=list)

    async def answer(
        self, context: ClientRequestContext, params: ElicitRequestParams
    ) -> ElicitResult:
        assert context
        assert isinstance(params, ElicitRequestFormParams)
        properties = params.requested_schema['properties']
        self.asked.append(frozenset(properties))
        if self.action != 'accept':
            return ElicitResult(action=self.action)

        return ElicitResult(
            action='accept', content={name: self.answers[name] for name in properties}
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketHarness:
    server: ServerHarness

    @property
    def ticket_file(self) -> anyio.Path:
        return anyio.Path(self.server.repository.joinpath(TICKET_PATH))

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        answerer: RecordingAnswerer | None = None,
    ) -> CallToolResult:
        answerer = answerer or RecordingAnswerer(answers={})
        server = self.server.create_server(create_catalog())
        async with Client(server, elicitation_callback=answerer.answer) as client:
            return await client.call_tool(name, arguments)

    async def current_branch(self) -> str:
        command = ['git', '-C', str(self.server.repository), 'symbolic-ref', '--short', 'HEAD']
        finished = await anyio.run_process(command)
        return finished.stdout.decode().strip()
