from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mcp.types import ToolAnnotations
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.icons import load_icon

from tests.mcp.investigation.investigation_harness import (
    KNOWN_ENTRY,
    OPEN_ENTRY,
    TARGET,
    create_investigation_harness,
)
from tests.mcp.server.server_harness import view_of

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.investigation.investigation_harness import InvestigationHarness
    from tests.mcp.server.server_harness import ServerHarness

WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
UNKNOWN = '20200101-nothing'
KNOWN_ROW = '| e1 | known | the drain loop sleeps | drain.py:12 | code-scout | 1 | '


def listed_tool_cases() -> pytest.MarkDecorator:
    tools: list[ParameterSet] = [
        pytest.param('investigation_start', 'Start an investigation', WRITES, id='start'),
        pytest.param('investigation_add', "Add to an investigation's ledger", WRITES, id='add'),
        pytest.param('investigation_render', "Show an investigation's ledger", READS, id='render'),
        pytest.param('investigation_knowns', 'Show the knowns table', READS, id='knowns'),
        pytest.param('investigation_list', 'List investigations', READS, id='list'),
    ]
    return pytest.mark.parametrize(('name', 'title', 'annotations'), tools)


def unknown_investigation_cases() -> pytest.MarkDecorator:
    calls: list[ParameterSet] = [
        pytest.param('investigation_render', id='render'),
        pytest.param('investigation_knowns', id='knowns'),
    ]
    return pytest.mark.parametrize('name', calls)


@pytest.fixture
def harness(server_harness: ServerHarness) -> InvestigationHarness:
    return create_investigation_harness(server_harness)


@pytest.fixture
async def started(harness: InvestigationHarness) -> str:
    await harness.commit('first')
    return await harness.start()


@pytest.fixture
async def recorded(harness: InvestigationHarness) -> None:
    await harness.record_repository()


class TestListedTools:
    async def test_are_the_five_investigation_tools(self, server_harness: ServerHarness) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}

        assert {name for name in names if name.startswith('investigation_')} == {
            'investigation_start',
            'investigation_add',
            'investigation_render',
            'investigation_knowns',
            'investigation_list',
        }

    @listed_tool_cases()
    async def test_carries_title_hints_and_icon(
        self,
        server_harness: ServerHarness,
        name: str,
        title: str,
        annotations: ToolAnnotations,
    ) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}

        tool = listed[name]
        assert (tool.title, tool.annotations) == (title, annotations)
        assert tool.icons == [load_icon('investigation')]


class TestInvestigationRender:
    async def test_shows_the_ledger_text(self, harness: InvestigationHarness, started: str) -> None:
        await harness.add(started, [dict(KNOWN_ENTRY), dict(OPEN_ENTRY)])

        view = view_of(await harness.call('investigation_render', {'investigation_id': started}))

        assert f'Target: {TARGET} (research)' in view['text']
        assert '- e1: the drain loop sleeps [drain.py:12] (code-scout, round 1)' in view['text']
        assert '- e2: why it sleeps (user, round 1)' in view['text']
        assert view['investigation_id'] == started

    async def test_asks_git_nothing(self, harness: InvestigationHarness, started: str) -> None:
        view_of(await harness.call('investigation_render', {'investigation_id': started}))

        assert harness.git_calls == []


class TestInvestigationKnowns:
    async def test_row_added_at_the_current_head_is_current(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        await harness.add(started, [dict(KNOWN_ENTRY)])

        view = view_of(await harness.call('investigation_knowns', {'investigation_id': started}))

        assert f'{KNOWN_ROW}current |' in view['text']

    async def test_row_added_at_another_head_is_a_lead(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        await harness.add(started, [dict(KNOWN_ENTRY)])
        await harness.commit('second')

        view = view_of(await harness.call('investigation_knowns', {'investigation_id': started}))

        assert f'{KNOWN_ROW}lead |' in view['text']

    async def test_limit_hides_the_rows_past_it(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        entries = [{**OPEN_ENTRY, 'text': f'question {number}'} for number in range(3)]
        await harness.add(started, entries)

        arguments = {'investigation_id': started, 'kinds': ['open'], 'limit': 1}
        view = view_of(await harness.call('investigation_knowns', arguments))

        assert '2 more rows; ask again with a larger limit' in view['text']

    async def test_asks_git_only_for_head(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        view_of(await harness.call('investigation_knowns', {'investigation_id': started}))

        assert harness.git_calls == ['resolve_head']


@pytest.mark.usefixtures('recorded')
class TestInvestigationList:
    @pytest.mark.usefixtures('started')
    async def test_lists_each_investigation_with_its_round(
        self, harness: InvestigationHarness, started: str
    ) -> None:
        await harness.add(started, [dict(OPEN_ENTRY)], round_number=2)

        view = view_of(await harness.call('investigation_list', {}))

        assert view['text'] == f'{started}\tround 2\n'

    async def test_empty_database_says_no_investigations(
        self, harness: InvestigationHarness
    ) -> None:
        view = view_of(await harness.call('investigation_list', {}))

        assert view['text'] == 'no investigations\n'

    async def test_asks_git_nothing(self, harness: InvestigationHarness) -> None:
        view_of(await harness.call('investigation_list', {}))

        assert harness.git_calls == []


class TestUnknownInvestigation:
    @unknown_investigation_cases()
    async def test_is_refused(self, harness: InvestigationHarness, name: str) -> None:
        result = await harness.call(name, {'investigation_id': UNKNOWN})

        assert result.is_error
