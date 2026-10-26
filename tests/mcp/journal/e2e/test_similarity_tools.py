from typing import TYPE_CHECKING

import pytest
from mcp.types import ToolAnnotations
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.icons import load_icon

from mcp import Client
from tests.mcp.journal.journal_harness import FIRST_ENTRY, create_journal_harness
from tests.mcp.server.server_harness import view_of

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.journal.journal_harness import JournalHarness
    from tests.mcp.server.server_harness import ServerHarness

READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
NO_MATCHES = 'no similar rows\n'


def empty_search_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param({'query': FIRST_ENTRY['root_cause'], 'kind': 'scout-report'}, id='kind'),
        pytest.param({'query': 'zebra giraffe quartz'}, id='unrelated'),
    ]
    return pytest.mark.parametrize('arguments', cases)


@pytest.fixture
def harness(server_harness: ServerHarness) -> JournalHarness:
    return create_journal_harness(server_harness)


class TestListedTool:
    async def test_carries_title_hints_and_icon(self, server_harness: ServerHarness) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

        tool = tools['similarity_search']
        assert (tool.title, tool.annotations) == ('Search for similar rows', READS)
        assert tool.icons == [load_icon('similarity')]


class TestSimilaritySearch:
    async def test_finds_a_journaled_crashout_by_its_root_cause(
        self, harness: JournalHarness
    ) -> None:
        await harness.add(FIRST_ENTRY)

        arguments = {'query': FIRST_ENTRY['root_cause']}
        view = view_of(await harness.call('similarity_search', arguments))

        [match] = view['matches']
        assert (match['kind'], match['reference']) == ('crashout', '#1')
        assert match['text'] == FIRST_ENTRY['root_cause']
        assert view['text'].startswith('crashout #1 (overlap ')

    @empty_search_cases()
    async def test_without_a_match_says_so(
        self, harness: JournalHarness, arguments: dict[str, str]
    ) -> None:
        await harness.add(FIRST_ENTRY)

        view = view_of(await harness.call('similarity_search', arguments))

        assert (view['text'], view['matches']) == (NO_MATCHES, [])

    async def test_asks_git_nothing(self, harness: JournalHarness) -> None:
        await harness.record_repository()

        view_of(await harness.call('similarity_search', {'query': 'anything'}))

        assert harness.git_calls == []
