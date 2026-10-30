from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mcp.types import ToolAnnotations
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.icons import load_icon

from tests.mcp.server.server_harness import view_of
from tests.mcp.ticket.ticket_harness import (
    ANSWERED,
    INTERVIEW,
    SLUG,
    TICKET_PATH,
    RecordingAnswerer,
    TicketHarness,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.mcp.server.server_harness import ServerHarness
    from tests.mcp.ticket.ticket_harness import (
        FormAction,
    )

STAGED_TEXT = f'staged {SLUG} (status staged, 0 investigations)\n'
WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
REPLACES = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
)
REFRESHES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


def without_stamp(section: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in section.items() if key != 'validated_at'}


def unanswered_action_cases() -> pytest.MarkDecorator:
    actions: list[ParameterSet] = [
        pytest.param('decline', id='decline'),
        pytest.param('cancel', id='cancel'),
    ]
    return pytest.mark.parametrize('action', actions)


def listed_tool_cases() -> pytest.MarkDecorator:
    tools: list[ParameterSet] = [
        pytest.param('ticket_write', 'Write a ticket', WRITES, id='write'),
        pytest.param('ticket_validate', 'Validate a ticket', REFRESHES, id='validate'),
        pytest.param('ticket_show', 'Show a ticket', READS, id='show'),
        pytest.param('ticket_update_context', "Update a ticket's context", REPLACES, id='context'),
    ]
    return pytest.mark.parametrize(('name', 'title', 'annotations'), tools)


@pytest.fixture
def harness(server_harness: ServerHarness) -> TicketHarness:
    return TicketHarness(server=server_harness)


@pytest.fixture
async def written(harness: TicketHarness) -> TicketHarness:
    view_of(await harness.call('ticket_write', dict(ANSWERED)))
    return harness


@pytest.fixture
async def staged(written: TicketHarness) -> TicketHarness:
    view_of(await written.call('ticket_validate', {'slug': SLUG}))
    return written


class TestListedTools:
    @listed_tool_cases()
    async def test_tool_carries_title_hints_and_ticket_icon(
        self, harness: TicketHarness, name: str, title: str, annotations: ToolAnnotations
    ) -> None:
        server = harness.server.create_server(create_catalog())
        async with Client(server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}

        tool = listed[name]
        assert (tool.title, tool.annotations) == (title, annotations)
        assert tool.icons == [load_icon('ticket')]


class TestTicketWrite:
    new_branch = MappingProxyType({
        'scope': 'large',
        'compaction': 'false',
        'branch': 'new',
        'branch_name': 'feat/tickets',
    })

    async def test_answered_call_writes_without_asking(self, harness: TicketHarness) -> None:
        answerer = RecordingAnswerer(answers={})

        view = view_of(await harness.call('ticket_write', dict(ANSWERED), answerer))

        assert view['text'] == f'wrote {TICKET_PATH}; review it, then run validate\n'
        assert answerer.asked == []
        assert await harness.ticket_file.is_file()

    async def test_one_form_asks_every_omitted_field(self, harness: TicketHarness) -> None:
        answerer = RecordingAnswerer(answers=dict(self.new_branch))

        view_of(await harness.call('ticket_write', dict(INTERVIEW), answerer))
        staged = view_of(await harness.call('ticket_validate', {'slug': SLUG}))['staged']

        assert answerer.asked == [frozenset(self.new_branch)]
        section = staged['section']
        assert (section['scope'], section['plan_first'], section['branch']) == (
            'large',
            False,
            'feat/tickets',
        )

    async def test_form_holds_only_the_omitted_fields(self, harness: TicketHarness) -> None:
        answerer = RecordingAnswerer(answers={'compaction': 'true'})
        arguments = {**INTERVIEW, 'scope': 'sm', 'branch': 'main'}

        view_of(await harness.call('ticket_write', arguments, answerer))

        assert answerer.asked == [frozenset({'compaction'})]

    async def test_current_branch_answer_takes_the_checkout_branch(
        self, harness: TicketHarness
    ) -> None:
        answers = {'scope': 'sm', 'compaction': 'true', 'branch': 'current', 'branch_name': ''}
        answerer = RecordingAnswerer(answers=answers)

        view_of(await harness.call('ticket_write', dict(INTERVIEW), answerer))
        staged = view_of(await harness.call('ticket_validate', {'slug': SLUG}))['staged']

        assert staged['section']['branch'] == await harness.current_branch()

    async def test_new_branch_without_a_name_is_refused(self, harness: TicketHarness) -> None:
        answers = {**self.new_branch, 'branch_name': ' '}

        result = await harness.call(
            'ticket_write', dict(INTERVIEW), RecordingAnswerer(answers=answers)
        )

        assert result.is_error
        assert 'a new branch needs a name' in str(result.content)
        assert not await harness.ticket_file.exists()

    async def test_long_branch_answer_is_refused_naming_the_field(
        self, harness: TicketHarness
    ) -> None:
        answers = {**self.new_branch, 'branch_name': 'b' * 256}

        result = await harness.call(
            'ticket_write', dict(INTERVIEW), RecordingAnswerer(answers=answers)
        )

        assert result.is_error
        assert 'branch_name is longer than 255 characters' in str(result.content)
        assert not await harness.ticket_file.exists()

    @unanswered_action_cases()
    async def test_unanswered_form_returns_the_needs_input_text(
        self, harness: TicketHarness, action: FormAction
    ) -> None:
        answerer = RecordingAnswerer(answers={}, action=action)

        view = view_of(await harness.call('ticket_write', dict(INTERVIEW), answerer))

        assert view['text'].startswith(NEEDS_INPUT)
        assert 'pass: branch (the current branch name, or the new branch name)\n' in view['text']
        assert not await harness.ticket_file.exists()

    async def test_existing_ticket_is_refused(self, written: TicketHarness) -> None:
        result = await written.call('ticket_write', dict(ANSWERED))

        assert result.is_error
        assert f'{TICKET_PATH} exists' in str(result.content)


class TestStagedTicket:
    async def test_validate_stages_the_written_ticket(self, written: TicketHarness) -> None:
        view = view_of(await written.call('ticket_validate', {'slug': SLUG}))

        assert view['text'] == f'valid; {STAGED_TEXT}'
        assert view['staged']['section']['ticket'] == TICKET_PATH

    async def test_show_returns_the_staged_record(self, staged: TicketHarness) -> None:
        view = view_of(await staged.call('ticket_show', {'slug': SLUG}))

        assert view['text'] == STAGED_TEXT
        assert view['staged']['slug'] == SLUG

    async def test_update_context_twice_with_the_same_lines_gives_the_same_ticket(
        self, staged: TicketHarness
    ) -> None:
        arguments = {'slug': SLUG, 'context': ['a new line']}
        first = view_of(await staged.call('ticket_update_context', arguments))

        second = view_of(await staged.call('ticket_update_context', arguments))

        assert without_stamp(second['staged']['section']) == without_stamp(
            first['staged']['section']
        )
        assert second['text'] == first['text']

    async def test_update_context_restages_with_the_new_lines(self, staged: TicketHarness) -> None:
        arguments = {'slug': SLUG, 'context': ['a new line']}

        view = view_of(await staged.call('ticket_update_context', arguments))

        assert view['text'] == f'context updated; {STAGED_TEXT}'
        assert view['staged']['section']['context'] == ['a new line']
        assert 'a new line' in await staged.ticket_file.read_text()

    async def test_validate_without_a_file_is_refused(self, harness: TicketHarness) -> None:
        result = await harness.call('ticket_validate', {'slug': SLUG})

        assert result.is_error
        assert 'run write first' in str(result.content)

    async def test_show_before_validate_is_refused(self, written: TicketHarness) -> None:
        result = await written.call('ticket_show', {'slug': SLUG})

        assert result.is_error
