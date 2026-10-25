"""The journal tools' shared e2e fixtures: a git-recording client harness and its entries."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from mcp import Client
from mightymodels_mcp.journal.use_cases import create_journal_work
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.entrypoint import create_catalog

from tests.mcp.server.server_harness import view_of
from tests.mcp.task.task_harness import RecordingOpener

if TYPE_CHECKING:
    from mcp.types import CallToolResult

    from tests.mcp.server.server_harness import ServerHarness

FIRST_ENTRY = MappingProxyType({
    'ticket': 'queue-drain',
    'branch': 'feat/drain',
    'severity': 'heated',
    'verdict': 'split',
    'rant': 'the drain loop slept through every retry',
    'failures': ['the retry never fired', 'the sleep hid the timeout'],
    'root_cause': 'the drain loop sleeps before it checks the queue',
    'corrective_action': 'check the queue before sleeping',
    'barked_back': True,
})
SECOND_ENTRY = MappingProxyType({
    'severity': 'full-meltdown',
    'verdict': 'deserved',
    'rant': 'the migration dropped a column twice',
    'failures': ['the column vanished'],
    'root_cause': 'schema scripts ran without a guard',
    'corrective_action': 'guard every schema script',
    'barked_back': False,
})


@dataclass(slots=True, kw_only=True, frozen=True)
class JournalHarness:
    server: ServerHarness
    opener: RecordingOpener

    @property
    def git_calls(self) -> list[str]:
        return self.opener.git_calls

    async def call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        self.git_calls.clear()
        server = create_server(ServerDependencies(state=self.opener), create_catalog())
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    async def record_repository(self) -> None:
        async with self.opener.open() as state:
            with create_journal_work(state).write():
                pass

    async def add(self, *entries: MappingProxyType[str, Any]) -> list[dict[str, Any]]:
        return [view_of(await self.call('crashout_add', dict(entry))) for entry in entries]


def create_journal_harness(server: ServerHarness) -> JournalHarness:
    opener = RecordingOpener(inner=server.dependencies.state)
    return JournalHarness(server=server, opener=opener)
