import json
from typing import TYPE_CHECKING

import anyio
import pytest
from mcp import Client
from mcp.types import ToolAnnotations
from mightymodels_core.snapshot import MAX_LIMIT
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.icons import load_icon

from tests.mcp.server.server_harness import view_of
from tests.mcp.task.task_harness import RecordingOpener, TaskHarness
from tests.mcp.ticket.ticket_harness import ANSWERED, SLUG, TicketHarness

if TYPE_CHECKING:
    from tests.mcp.server.server_harness import ServerHarness

HANDOFFS = f'.mightymodels/{SLUG}/handoffs'
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
QUERIES = ['refusal', 'current_branch', 'resolve_head', 'dirty_paths']


def refused_limit_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'limit', [pytest.param(0, id='zero'), pytest.param(MAX_LIMIT + 1, id='one-over-max')]
    )


@pytest.fixture
async def harness(server_harness: ServerHarness) -> TaskHarness:
    tickets = TicketHarness(server=server_harness)
    view_of(await tickets.call('ticket_write', dict(ANSWERED)))
    view_of(await tickets.call('ticket_validate', {'slug': SLUG}))
    opener = RecordingOpener(inner=server_harness.dependencies.state)
    return TaskHarness(server=server_harness, opener=opener)


@pytest.fixture
async def head(harness: TaskHarness) -> str:
    return await harness.commit('first')


class TestListedTool:
    async def test_carries_title_hints_and_snapshot_icon(
        self, server_harness: ServerHarness
    ) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}

        tool = listed['snapshot_take']
        assert (tool.title, tool.annotations) == ('Take a snapshot', READS)
        assert tool.icons == [load_icon('snapshot')]


@pytest.mark.usefixtures('head')
class TestSnapshotTake:
    async def test_renders_the_header_with_the_branch_and_head_git_answered(
        self, harness: TaskHarness, head: str
    ) -> None:
        branch = await harness.git('branch', '--show-current')

        view = view_of(await harness.call('snapshot_take', {'slug': SLUG}))

        assert view['text'].startswith(f'# Snapshot for {SLUG}\n')
        assert f'Repository: {branch} at {head[:7]}' in view['text']

    async def test_record_is_json_naming_the_same_slug(self, harness: TaskHarness) -> None:
        view = view_of(await harness.call('snapshot_take', {'slug': SLUG}))

        assert json.loads(view['record'])['slug'] == SLUG

    async def test_returns_the_handoff_paths_and_writes_neither_file(
        self, harness: TaskHarness
    ) -> None:
        view = view_of(await harness.call('snapshot_take', {'slug': SLUG}))

        assert view['markdown_path'] == f'{HANDOFFS}/snapshot.md'
        assert view['record_path'] == f'{HANDOFFS}/snapshot.json'
        for path in (view['markdown_path'], view['record_path']):
            assert not await anyio.Path(harness.server.repository, path).exists()

    async def test_asks_git_exactly_the_four_queries(self, harness: TaskHarness) -> None:
        view_of(await harness.call('snapshot_take', {'slug': SLUG}))

        assert harness.git_calls == QUERIES

    async def test_dirty_tree_longer_than_the_limit_lists_only_the_limit(
        self, harness: TaskHarness
    ) -> None:
        for number in range(5):
            await anyio.Path(harness.server.repository, f'dirty{number}.txt').write_text('x\n')

        view = view_of(await harness.call('snapshot_take', {'slug': SLUG, 'limit': 2}))

        assert view['text'].count('- changed: ') == 2

    async def test_unstaged_slug_is_refused(self, harness: TaskHarness) -> None:
        result = await harness.call('snapshot_take', {'slug': 'no-such-ticket'})

        assert result.is_error

    async def test_path_shaped_slug_is_refused(self, harness: TaskHarness) -> None:
        result = await harness.call('snapshot_take', {'slug': '../../etc'})

        assert result.is_error
        assert harness.git_calls == []

    @refused_limit_cases()
    async def test_limit_outside_the_bounds_is_refused(
        self, harness: TaskHarness, limit: int
    ) -> None:
        result = await harness.call('snapshot_take', {'slug': SLUG, 'limit': limit})

        assert result.is_error
        assert harness.git_calls == []
