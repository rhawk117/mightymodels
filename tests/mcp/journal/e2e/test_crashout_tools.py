from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pytest
from mcp.types import ToolAnnotations
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.icons import load_icon

from mcp import Client
from tests.mcp.journal.journal_harness import FIRST_ENTRY, SECOND_ENTRY, create_journal_harness
from tests.mcp.server.server_harness import view_of

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.journal.journal_harness import JournalHarness
    from tests.mcp.server.server_harness import ServerHarness

WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


@dataclass(slots=True, kw_only=True, frozen=True)
class ListedTool:
    name: str
    title: str
    annotations: ToolAnnotations

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def listed_tool_cases() -> pytest.MarkDecorator:
    tools = [
        ListedTool(name='crashout_add', title='Journal a crashout', annotations=WRITES),
        ListedTool(name='crashout_stats', title='Show crashout patterns', annotations=READS),
        ListedTool(name='crashout_last', title='Show the last crashout', annotations=READS),
    ]
    return pytest.mark.parametrize('listed', [tool.param for tool in tools])


def refused_add_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param({'rant': '  \n '}, id='blank-rant'),
        pytest.param({'failures': []}, id='no-failures'),
        pytest.param({'failures': ['   ']}, id='blank-failure'),
        pytest.param({'root_cause': ' '}, id='blank-root-cause'),
        pytest.param({'corrective_action': ' '}, id='blank-action'),
        pytest.param({'unknown': 1}, id='unknown-argument'),
    ]
    return pytest.mark.parametrize('changes', cases)


def crashout_tool_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param('crashout_add', dict(FIRST_ENTRY), id='add'),
        pytest.param('crashout_stats', {}, id='stats'),
        pytest.param('crashout_last', {}, id='last'),
    ]
    return pytest.mark.parametrize(('name', 'arguments'), cases)


@pytest.fixture
def harness(server_harness: ServerHarness) -> JournalHarness:
    return create_journal_harness(server_harness)


@pytest.fixture
async def recorded(harness: JournalHarness) -> None:
    await harness.record_repository()


class TestListedTools:
    async def test_are_the_three_crashout_tools(self, server_harness: ServerHarness) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}

        assert {name for name in names if name.startswith('crashout_')} == {
            'crashout_add',
            'crashout_stats',
            'crashout_last',
        }

    @listed_tool_cases()
    async def test_carries_title_hints_and_icon(
        self, server_harness: ServerHarness, listed: ListedTool
    ) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

        tool = tools[listed.name]
        assert (tool.title, tool.annotations) == (listed.title, listed.annotations)
        assert tool.icons == [load_icon('crashout')]


class TestCrashoutAdd:
    async def test_returns_the_journaled_text_and_number(self, harness: JournalHarness) -> None:
        [view] = await harness.add(FIRST_ENTRY)

        assert view['text'] == 'journaled crashout #1\n'

    async def test_second_add_numbers_on(self, harness: JournalHarness) -> None:
        _first, second = await harness.add(FIRST_ENTRY, SECOND_ENTRY)

        assert second['text'] == 'journaled crashout #2\n'

    @refused_add_cases()
    async def test_is_refused(self, harness: JournalHarness, changes: dict[str, Any]) -> None:
        result = await harness.call('crashout_add', {**FIRST_ENTRY, **changes})

        assert result.is_error


@pytest.mark.usefixtures('recorded')
class TestCrashoutStats:
    async def test_empty_journal_is_serenity(self, harness: JournalHarness) -> None:
        view = view_of(await harness.call('crashout_stats', {}))

        assert view['text'] == 'no crashouts recorded yet. serenity.\n'

    async def test_shows_the_counts_failures_and_standing_actions(
        self, harness: JournalHarness
    ) -> None:
        await harness.add(FIRST_ENTRY, SECOND_ENTRY)

        text = view_of(await harness.call('crashout_stats', {}))['text']

        assert 'entries: 2' in text
        assert 'severity: heated=1 full-meltdown=1' in text
        assert 'barked_back: 1/2' in text
        assert '| split | heated] the retry never fired' in text
        assert '| deserved | full-meltdown] the column vanished' in text
        assert '  - check the queue before sleeping' in text
        assert '  - guard every schema script' in text


@pytest.mark.usefixtures('recorded')
class TestCrashoutLast:
    async def test_empty_journal_says_nothing_journaled(self, harness: JournalHarness) -> None:
        view = view_of(await harness.call('crashout_last', {}))

        assert view['text'] == 'no crashouts recorded yet.\n'

    async def test_shows_the_newest_entry_and_its_structure(self, harness: JournalHarness) -> None:
        await harness.add(FIRST_ENTRY, SECOND_ENTRY)

        view = view_of(await harness.call('crashout_last', {}))

        assert 'root_cause: schema scripts ran without a guard' in view['text']
        assert view['entry']['severity'] == 'full-meltdown'
        assert view['entry']['failures'] == ['the column vanished']
        assert view['entry']['ticket'] is None


@pytest.mark.usefixtures('recorded')
class TestCrashoutLastTicketAndBranch:
    ticket = 'mcp-per-action-tools'
    branch = 'feat/journal-mapping'

    @pytest.fixture
    async def journaled(self, harness: JournalHarness) -> None:
        await harness.add(
            MappingProxyType({**FIRST_ENTRY, 'ticket': self.ticket, 'branch': self.branch})
        )

    @pytest.mark.usefixtures('journaled')
    async def test_crashout_last_keeps_ticket_and_branch_apart(
        self, harness: JournalHarness
    ) -> None:
        view = view_of(await harness.call('crashout_last', {}))

        assert (view['entry']['ticket'], view['entry']['branch']) == (self.ticket, self.branch)
        assert f'ticket: {self.ticket}' in view['text']
        assert f'branch: {self.branch}' in view['text']


class TestGit:
    @crashout_tool_cases()
    async def test_no_crashout_tool_asks_git(
        self, harness: JournalHarness, name: str, arguments: dict[str, Any]
    ) -> None:
        await harness.record_repository()

        await harness.call(name, arguments)

        assert harness.git_calls == []
