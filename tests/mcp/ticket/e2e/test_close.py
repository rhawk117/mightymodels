import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from mcp import Client
from mcp.types import ToolAnnotations
from mightymodels_core.primitives import TaskId
from mightymodels_core.tasks import Attempt, Transition
from mightymodels_mcp.server.entrypoint import create_catalog
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.ticket.use_cases import create_ticket_work

from tests.mcp.server.server_harness import view_of
from tests.mcp.ticket.ticket_harness import ANSWERED, SLUG, TicketHarness

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.server.server_harness import ServerHarness

READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
CLOSES = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)
NO_WORK = 'no verified task work is recorded'
TASK = TaskId('T1')
ARCHIVE = f'.mightymodels/archives/{SLUG}'


def listed_tool_cases() -> pytest.MarkDecorator:
    tools: list[ParameterSet] = [
        pytest.param('close_check', 'Check a ticket for live work', READS, id='check'),
        pytest.param('close_ticket', 'Close a ticket', CLOSES, id='close'),
    ]
    return pytest.mark.parametrize(('name', 'title', 'annotations'), tools)


async def verify_task(server: ServerHarness) -> None:
    moment = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
    verified = Transition(
        task_key=TASK, before='pending', after='verified', reasons=(), head=None, at=moment
    )
    attempt = Attempt(worker='engineer', mode=None, owned=())
    async with server.dependencies.state.open() as state:
        with create_ticket_work(state).write() as unit:
            ticket_id = unit.tickets.show(SLUG).id
            unit.closing.tasks.record_start(ticket_id, verified, attempt)


@pytest.fixture
async def staged(server_harness: ServerHarness) -> TicketHarness:
    harness = TicketHarness(server=server_harness)
    view_of(await harness.call('ticket_write', dict(ANSWERED)))
    view_of(await harness.call('ticket_validate', {'slug': SLUG}))
    return harness


@pytest.fixture
async def ready(staged: TicketHarness) -> TicketHarness:
    await verify_task(staged.server)
    return staged


async def read_archive(harness: TicketHarness, name: str) -> str:
    return await anyio.Path(harness.server.repository.joinpath(name)).read_text()


class TestListedTools:
    @listed_tool_cases()
    async def test_tool_carries_title_hints_and_close_icon(
        self, server_harness: ServerHarness, name: str, title: str, annotations: ToolAnnotations
    ) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}

        tool = listed[name]
        assert (tool.title, tool.annotations) == (title, annotations)
        assert tool.icons == [load_icon('close')]


class TestCloseCheck:
    async def test_unstarted_ticket_lists_what_blocks_it(self, staged: TicketHarness) -> None:
        view = view_of(await staged.call('close_check', {'slug': SLUG}))

        assert view['blocked']
        assert view['blockers'] == [NO_WORK]
        assert view['text'] == f'live work remains\n  - {NO_WORK}\n'

    async def test_verified_ticket_has_no_live_work(self, ready: TicketHarness) -> None:
        view = view_of(await ready.call('close_check', {'slug': SLUG}))

        assert view['text'] == f'{SLUG} has no live work\n'
        assert not view['blocked']

    async def test_unstaged_ticket_is_refused(self, server_harness: ServerHarness) -> None:
        result = await TicketHarness(server=server_harness).call('close_check', {'slug': SLUG})

        assert result.is_error


class TestCloseTicket:
    async def test_blocked_close_writes_nothing(self, staged: TicketHarness) -> None:
        view = view_of(await staged.call('close_ticket', {'slug': SLUG, 'shipped': 'done'}))

        assert view['text'] == f'not closed; live work remains\n  - {NO_WORK}\n'
        assert view['archive'] is None
        assert not await anyio.Path(staged.server.repository, ARCHIVE + '.md').exists()

    async def test_close_writes_the_archive_markdown_and_record(self, ready: TicketHarness) -> None:
        arguments = {'slug': SLUG, 'shipped': 'the close tools', 'gotchas': ['mind the order']}

        view = view_of(await ready.call('close_ticket', arguments))

        assert view['text'] == f'closed {SLUG}; archive at {ARCHIVE}.md\n'
        assert view['archive'] == {
            'markdown_path': f'{ARCHIVE}.md',
            'record_path': f'{ARCHIVE}.json',
        }
        markdown = await read_archive(ready, f'{ARCHIVE}.md')
        assert markdown.startswith(f'# {SLUG}\n')
        assert 'mind the order' in markdown
        record: dict[str, Any] = json.loads(await read_archive(ready, f'{ARCHIVE}.json'))
        assert record['closing']['shipped'] == 'the close tools'

    async def test_second_close_is_refused_and_keeps_the_archive(
        self, ready: TicketHarness
    ) -> None:
        view_of(await ready.call('close_ticket', {'slug': SLUG, 'shipped': 'first'}))

        result = await ready.call('close_ticket', {'slug': SLUG, 'shipped': 'second'})

        assert result.is_error
        assert 'first' in await read_archive(ready, f'{ARCHIVE}.md')

    async def test_missing_shipped_line_is_refused(self, ready: TicketHarness) -> None:
        result = await ready.call('close_ticket', {'slug': SLUG})

        assert result.is_error
        assert 'shipped is required' in str(result.content)
