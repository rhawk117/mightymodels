from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import pytest
from mcp.types import ElicitRequestFormParams, ElicitResult, ToolAnnotations
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.icons import load_icon

from mcp import Client
from tests.mcp.server.server_harness import view_of
from tests.mcp.task.task_harness import RecordingOpener
from tests.mcp.ticket.ticket_harness import ANSWERED, SLUG, TicketHarness

if TYPE_CHECKING:
    from collections.abc import Mapping

    from _pytest.mark import ParameterSet
    from mcp.client.session import ClientRequestContext
    from mcp.types import CallToolResult, ElicitRequestParams

    from tests.mcp.server.server_harness import ServerHarness

type FormAction = Literal['accept', 'decline', 'cancel']

WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
CHECK = MappingProxyType({'id': 'T1.check', 'argv': ('uv', 'run', 'pytest', '-q')})
LINT = MappingProxyType({'id': 'T1.lint', 'argv': ('uv', 'run', 'ruff', 'check')})
STATUS = MappingProxyType({'slug': SLUG})
FORM_MESSAGE = (
    'Approve these verification commands?\nT1.check: uv run pytest -q\nT1.lint: uv run ruff check'
)


@dataclass(slots=True, kw_only=True, frozen=True)
class FormAnswerer:
    answer: str = 'approve'
    action: FormAction = 'accept'
    messages: list[str] = field(default_factory=list)
    fields: list[frozenset[str]] = field(default_factory=list)

    async def respond(
        self, context: ClientRequestContext, params: ElicitRequestParams
    ) -> ElicitResult:
        assert context
        assert isinstance(params, ElicitRequestFormParams)
        self.messages.append(params.message)
        self.fields.append(frozenset(params.requested_schema['properties']))
        if self.action != 'accept':
            return ElicitResult(action=self.action)

        return ElicitResult(action='accept', content={'approval': self.answer})


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractHarness:
    opener: RecordingOpener

    @property
    def git_calls(self) -> list[str]:
        return self.opener.git_calls

    async def call(
        self, name: str, arguments: dict[str, Any], answerer: FormAnswerer | None = None
    ) -> CallToolResult:
        self.git_calls.clear()
        answerer = answerer or FormAnswerer()
        server = create_server(ServerDependencies(state=self.opener), create_catalog())
        async with Client(server, elicitation_callback=answerer.respond) as client:
            return await client.call_tool(name, arguments)

    async def status_rows(self) -> list[str]:
        view = view_of(await self.call('contract_status', dict(STATUS)))
        return view['text'].splitlines()[1:]


def create_approve(*commands: Mapping[str, Any]) -> dict[str, Any]:
    return {'slug': SLUG, 'commands': [dict(command) for command in commands]}


def unanswered_action_cases() -> pytest.MarkDecorator:
    actions: list[ParameterSet] = [
        pytest.param('decline', id='decline'),
        pytest.param('cancel', id='cancel'),
    ]
    return pytest.mark.parametrize('action', actions)


def listed_tool_cases() -> pytest.MarkDecorator:
    tools: list[ParameterSet] = [
        pytest.param('contract_approve', 'Approve the contract commands', WRITES, id='approve'),
        pytest.param('contract_status', 'Show the contract status', READS, id='status'),
    ]
    return pytest.mark.parametrize(('name', 'title', 'annotations'), tools)


@pytest.fixture
async def harness(server_harness: ServerHarness) -> ContractHarness:
    tickets = TicketHarness(server=server_harness)
    view_of(await tickets.call('ticket_write', dict(ANSWERED)))
    view_of(await tickets.call('ticket_validate', {'slug': SLUG}))
    return ContractHarness(opener=RecordingOpener(inner=server_harness.dependencies.state))


@pytest.fixture
async def approved(harness: ContractHarness) -> ContractHarness:
    view_of(await harness.call('contract_approve', create_approve(CHECK, LINT)))
    return harness


class TestListedTools:
    @listed_tool_cases()
    async def test_tool_carries_title_hints_and_contract_icon(
        self, server_harness: ServerHarness, name: str, title: str, annotations: ToolAnnotations
    ) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}

        assert (listed[name].title, listed[name].annotations) == (title, annotations)
        assert listed[name].icons == [load_icon('contract')]


class TestContractApprove:
    async def test_form_lists_every_command_and_approving_records_them(
        self, harness: ContractHarness
    ) -> None:
        answerer = FormAnswerer()

        view = view_of(
            await harness.call('contract_approve', create_approve(CHECK, LINT), answerer)
        )

        assert (view['text'], view['passing']) == ('contract: 2 commands (2 new)\n', True)
        assert (answerer.messages, answerer.fields) == ([FORM_MESSAGE], [frozenset({'approval'})])
        assert await harness.status_rows() == ['T1.check never-run', 'T1.lint never-run']

    async def test_named_approvers_ask_nothing(self, harness: ContractHarness) -> None:
        answerer = FormAnswerer()
        named = [{**command, 'approved_by': 'lead'} for command in (CHECK, LINT)]

        view = view_of(await harness.call('contract_approve', create_approve(*named), answerer))

        assert view['text'] == 'contract: 2 commands (2 new)\n'
        assert answerer.messages == []

    async def test_declining_the_choice_records_nothing(self, harness: ContractHarness) -> None:
        answerer = FormAnswerer(answer='decline')

        view = view_of(
            await harness.call('contract_approve', create_approve(CHECK, LINT), answerer)
        )

        assert (view['text'], view['passing']) == (
            'not approved: the user chose to decline; revise the commands, then call again\n',
            False,
        )
        assert await harness.status_rows() == ['no matching commands']

    @unanswered_action_cases()
    async def test_unanswered_form_returns_the_needs_input_text(
        self, harness: ContractHarness, action: FormAction
    ) -> None:
        view = view_of(
            await harness.call(
                'contract_approve', create_approve(CHECK, LINT), FormAnswerer(action=action)
            )
        )

        assert view['passing'] is False
        assert view['text'] == (
            f'{NEEDS_INPUT}\n{FORM_MESSAGE}\nchoices: approve, decline\n'
            'pass: approved_by "user" on each command, once the user approved\n'
        )
        assert await harness.status_rows() == ['no matching commands']

    async def test_repeat_call_reads_no_new_commands(self, approved: ContractHarness) -> None:
        view = view_of(await approved.call('contract_approve', create_approve(CHECK, LINT)))

        assert view['text'] == 'contract: 2 commands (0 new)\n'

    async def test_changed_argv_is_refused(self, approved: ContractHarness) -> None:
        changed = {**CHECK, 'argv': ('uv', 'run', 'pytest')}

        result = await approved.call('contract_approve', create_approve(changed))

        assert result.is_error
        assert 'T1.check' in str(result.content)

    async def test_asks_git_only_for_head(self, harness: ContractHarness) -> None:
        view_of(await harness.call('contract_approve', create_approve(CHECK, LINT)))

        assert harness.git_calls == ['resolve_head']


class TestContractStatus:
    async def test_shows_each_command_with_its_state(self, approved: ContractHarness) -> None:
        view = view_of(await approved.call('contract_status', dict(STATUS)))

        assert view['text'].splitlines()[1:] == ['T1.check never-run', 'T1.lint never-run']
        assert view['passing'] is False
        assert [(row['id'], row['argv'], row['state']) for row in view['commands']] == [
            ('T1.check', list(CHECK['argv']), 'never-run'),
            ('T1.lint', list(LINT['argv']), 'never-run'),
        ]

    async def test_header_names_the_short_head(self, approved: ContractHarness) -> None:
        view = view_of(await approved.call('contract_status', dict(STATUS)))

        assert view['text'].startswith('HEAD unknown\n')

    async def test_ticket_without_commands_has_none_to_show(self, harness: ContractHarness) -> None:
        view = view_of(await harness.call('contract_status', dict(STATUS)))

        assert view['text'] == 'HEAD unknown\nno matching commands\n'

    async def test_asks_git_only_for_head(self, approved: ContractHarness) -> None:
        view_of(await approved.call('contract_status', dict(STATUS)))

        assert approved.git_calls == ['resolve_head']
