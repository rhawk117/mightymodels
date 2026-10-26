import re
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from mightymodels_core.database.errors import NestedUnitError
from mightymodels_mcp.main import create_catalog

from mcp import Client
from tests.mcp.investigation.investigation_harness import TARGET
from tests.mcp.journal.journal_harness import FIRST_ENTRY, create_journal_harness
from tests.mcp.server.server_harness import view_of

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.types import CallToolResult

    from tests.mcp.server.server_harness import ServerHarness

type ToolCall = tuple[str, dict[str, Any]]


def result_text(result: CallToolResult) -> str:
    return '\n'.join(str(block) for block in result.content)


class TestConcurrentCalls:
    writes = 6
    reads = 4
    seconds = 30
    nested_message = str(NestedUnitError())
    crashout_number = re.compile(r'journaled crashout #(\d+)')

    @property
    def calls(self) -> list[ToolCall]:
        added: list[ToolCall] = [('crashout_add', dict(FIRST_ENTRY))] * self.writes
        started: list[ToolCall] = [
            ('investigation_start', {'target': TARGET, 'kind': 'research'})
        ] * self.writes
        read_calls: list[ToolCall] = [
            ('crashout_stats', {}),
            ('crashout_last', {}),
            ('similarity_search', {'query': 'drain'}),
            ('investigation_list', {}),
        ]
        return [*added, *started, *(read_calls * self.reads)]

    @pytest.fixture
    async def client(self, server_harness: ServerHarness) -> AsyncIterator[Client]:
        await create_journal_harness(server_harness).record_repository()
        server = server_harness.create_server(create_catalog())
        async with Client(server) as connected:
            yield connected

    async def collect_results(self, client: Client) -> list[CallToolResult]:
        results: list[CallToolResult] = []

        async def run(name: str, arguments: dict[str, Any]) -> None:
            results.append(await client.call_tool(name, arguments))

        with anyio.fail_after(self.seconds):
            async with anyio.create_task_group() as group:
                for name, arguments in self.calls:
                    group.start_soon(run, name, arguments)
        return results

    @pytest.fixture
    async def results(self, client: Client) -> list[CallToolResult]:
        return await self.collect_results(client)

    async def test_every_call_completes_without_an_error(
        self, results: list[CallToolResult]
    ) -> None:
        assert len(results) == len(self.calls)
        assert [result_text(result) for result in results if result.is_error] == []

    async def test_no_call_reports_a_nested_unit(self, results: list[CallToolResult]) -> None:
        assert [r for r in results if self.nested_message in result_text(r)] == []

    async def test_every_crashout_lands_once(self, results: list[CallToolResult]) -> None:
        texts = [view_of(result)['text'] for result in results]
        numbers = sorted(int(number) for number in self.crashout_number.findall('\n'.join(texts)))
        assert numbers == list(range(1, self.writes + 1))

    def started_ids(self, results: list[CallToolResult]) -> list[str]:
        views = [view_of(result) for result in results]
        return [view['investigation_id'] for view in views if view.get('investigation_id')]

    async def test_every_investigation_gets_its_own_id(self, results: list[CallToolResult]) -> None:
        assert len(set(self.started_ids(results))) == self.writes

    async def test_reads_after_the_batch_count_every_write(
        self, client: Client, results: list[CallToolResult]
    ) -> None:
        stats = view_of(await client.call_tool('crashout_stats', {}))
        arguments = [{'investigation_id': found} for found in self.started_ids(results)]
        rendered = [await client.call_tool('investigation_render', one) for one in arguments]

        assert f'entries: {self.writes}\n' in stats['text']
        assert [result_text(r) for r in rendered if r.is_error] == []
