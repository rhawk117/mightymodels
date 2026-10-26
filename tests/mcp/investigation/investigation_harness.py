"""The investigation tools' shared e2e fixtures: a git-recording client harness and its entries."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import anyio
from mcp import Client
from mightymodels_mcp.investigation.use_cases import create_investigation_work
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies

from tests.mcp.server.server_harness import view_of
from tests.mcp.task.task_harness import RecordingOpener
from tests.mcp.ticket.ticket_harness import RecordingAnswerer

if TYPE_CHECKING:
    from mcp.types import CallToolResult

    from tests.mcp.server.server_harness import ServerHarness

TARGET = 'queue drains slowly'
KNOWN_ENTRY = MappingProxyType({
    'kind': 'known',
    'text': 'the drain loop sleeps',
    'source': 'code-scout',
    'cite': 'drain.py:12',
})
OPEN_ENTRY = MappingProxyType({'kind': 'open', 'text': 'why it sleeps', 'source': 'user'})


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationHarness:
    server: ServerHarness
    opener: RecordingOpener

    @property
    def git_calls(self) -> list[str]:
        return self.opener.git_calls

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        answerer: RecordingAnswerer | None = None,
    ) -> CallToolResult:
        answerer = answerer or RecordingAnswerer(answers={})
        self.git_calls.clear()
        server = create_server(ServerDependencies(state=self.opener), create_catalog())
        async with Client(server, elicitation_callback=answerer.answer) as client:
            return await client.call_tool(name, arguments)

    async def commit(self, message: str) -> str:
        identity = ['-c', 'user.name=probe', '-c', 'user.email=probe@example.com']
        repository = str(self.server.repository)
        base = ['git', '-C', repository, *identity]
        await anyio.run_process([*base, 'commit', '--allow-empty', '--quiet', '-m', message])
        finished = await anyio.run_process([*base, 'rev-parse', 'HEAD'])
        return finished.stdout.decode().strip()

    async def record_repository(self) -> None:
        async with self.opener.open() as state:
            with create_investigation_work(state).write():
                pass

    async def start(self, kind: str = 'research') -> str:
        view = view_of(await self.call('investigation_start', {'target': TARGET, 'kind': kind}))
        return view['investigation_id']

    async def add(
        self, investigation: str, entries: list[dict[str, Any]], round_number: int = 1
    ) -> None:
        arguments = {'investigation_id': investigation, 'round': round_number, 'entries': entries}
        view_of(await self.call('investigation_add', arguments))


def create_investigation_harness(server: ServerHarness) -> InvestigationHarness:
    opener = RecordingOpener(inner=server.dependencies.state)
    return InvestigationHarness(server=server, opener=opener)
