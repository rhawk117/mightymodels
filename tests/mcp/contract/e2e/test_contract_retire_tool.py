import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import pytest
from mcp import Client
from mcp.types import ElicitRequestFormParams, ElicitResult
from mightymodels_core.edge import DATABASE_NAME
from mightymodels_mcp.forms.needs_input import NEEDS_INPUT
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies

from tests.mcp.server.server_harness import view_of
from tests.mcp.task.task_harness import RecordingOpener
from tests.mcp.ticket.ticket_harness import ANSWERED, SLUG, TicketHarness

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mcp.client.session import ClientRequestContext
    from mcp.types import CallToolResult, ElicitRequestParams

    from tests.mcp.server.server_harness import ServerHarness

type FormAction = Literal['accept', 'decline', 'cancel']

CHECK = MappingProxyType({'id': 'I1', 'argv': ('uv', 'run', 'pytest', '-q')})
LINT = MappingProxyType({'id': 'I2', 'argv': ('uv', 'run', 'ruff', 'check')})
WHY = 'the check moved to another command'
RETIRE = MappingProxyType({'slug': SLUG, 'id': 'I1', 'why': WHY})
FORM_TITLE = f'Retire this verification command?\nI1: {WHY}'


@dataclass(slots=True, kw_only=True, frozen=True)
class FormAnswerer:
    answer: str = 'approve'
    action: FormAction = 'accept'
    messages: list[str] = field(default_factory=list)

    async def respond(
        self, context: ClientRequestContext, params: ElicitRequestParams
    ) -> ElicitResult:
        assert context
        assert isinstance(params, ElicitRequestFormParams)
        self.messages.append(params.message)
        if self.action != 'accept':
            return ElicitResult(action=self.action)

        return ElicitResult(action='accept', content={'approval': self.answer})


@dataclass(slots=True, kw_only=True, frozen=True)
class RetireHarness:
    opener: RecordingOpener

    async def call(
        self, name: str, arguments: dict[str, Any], answerer: FormAnswerer | None = None
    ) -> CallToolResult:
        answerer = answerer or FormAnswerer()
        server = create_server(ServerDependencies(state=self.opener), create_catalog())
        async with Client(server, elicitation_callback=answerer.respond) as client:
            return await client.call_tool(name, arguments)

    async def retire(self, answerer: FormAnswerer | None = None, **extra: str) -> CallToolResult:
        return await self.call('contract_retire', {**RETIRE, **extra}, answerer)

    async def status(self) -> dict[str, Any]:
        return view_of(await self.call('contract_status', {'slug': SLUG}))


def retirements_of(server_harness: ServerHarness) -> list[tuple[str, str | None, str | None]]:
    with closing(sqlite3.connect(server_harness.data_directory / DATABASE_NAME)) as connection:
        rows = connection.execute(
            'SELECT command_key, retired_by, retired_approval_source FROM contract_commands'
            ' ORDER BY command_key'
        ).fetchall()
    return [(key, by, source) for key, by, source in rows]


def unanswered_action_cases() -> pytest.MarkDecorator:
    actions: list[ParameterSet] = [pytest.param('cancel', id='cancel')]
    return pytest.mark.parametrize('action', actions)


@pytest.fixture
async def harness(server_harness: ServerHarness) -> RetireHarness:
    tickets = TicketHarness(server=server_harness)
    view_of(await tickets.call('ticket_write', dict(ANSWERED)))
    view_of(await tickets.call('ticket_validate', {'slug': SLUG}))
    opener = RecordingOpener(inner=server_harness.dependencies.state)
    created = RetireHarness(opener=opener)
    commands = [dict(CHECK), dict(LINT)]
    view_of(await created.call('contract_approve', {'slug': SLUG, 'commands': commands}))
    return created


class TestContractRetire:
    async def test_form_approval_retires_with_source_form_by_user(
        self, harness: RetireHarness, server_harness: ServerHarness
    ) -> None:
        answerer = FormAnswerer()

        view = view_of(await harness.retire(answerer))

        assert (view['text'], view['passing']) == (
            f'retired I1 (form, by user): {WHY}\n',
            True,
        )
        assert answerer.messages == ['Retire this verification command?']
        assert retirements_of(server_harness) == [('I1', 'user', 'form'), ('I2', None, None)]

    async def test_declined_form_retires_nothing(
        self, harness: RetireHarness, server_harness: ServerHarness
    ) -> None:
        view = view_of(await harness.retire(FormAnswerer(answer='decline')))

        assert (view['text'], view['passing']) == (
            'not approved: the user chose to decline; revise the commands, then call again\n',
            False,
        )
        assert retirements_of(server_harness) == [('I1', None, None), ('I2', None, None)]

    @unanswered_action_cases()
    async def test_unanswered_form_returns_the_needs_input_text(
        self, harness: RetireHarness, server_harness: ServerHarness, action: FormAction
    ) -> None:
        view = view_of(await harness.retire(FormAnswerer(action=action)))

        assert view['passing'] is False
        assert view['text'] == (
            f'{NEEDS_INPUT}\n{FORM_TITLE}\nchoices: approve, decline\n'
            'pass: approved_by "user", once the user approved\n'
        )
        assert retirements_of(server_harness) == [('I1', None, None), ('I2', None, None)]

    async def test_named_approver_asks_no_form_and_records_fallback(
        self, harness: RetireHarness, server_harness: ServerHarness
    ) -> None:
        answerer = FormAnswerer()

        view = view_of(await harness.retire(answerer, approved_by='lead'))

        assert view['text'] == f'retired I1 (fallback, by lead): {WHY}\n'
        assert answerer.messages == []
        assert retirements_of(server_harness) == [('I1', 'lead', 'fallback'), ('I2', None, None)]

    async def test_unknown_id_is_refused(self, harness: RetireHarness) -> None:
        result = await harness.retire(id='I9', approved_by='lead')

        assert result.is_error
        assert 'I9' in str(result.content)

    async def test_already_retired_id_is_refused(self, harness: RetireHarness) -> None:
        view_of(await harness.retire(approved_by='lead'))

        result = await harness.retire(approved_by='lead')

        assert result.is_error
        assert 'already retired' in str(result.content)


class TestStatusShowsRetired:
    async def test_retired_command_is_listed_apart_from_live_ones(
        self, harness: RetireHarness
    ) -> None:
        view_of(await harness.retire(approved_by='lead'))

        view = await harness.status()

        assert [row['id'] for row in view['commands']] == ['I2']
        assert [
            (row['id'], row['by'], row['why'], row['approval_source']) for row in view['retired']
        ] == [('I1', 'lead', WHY, 'fallback')]
        assert view['text'].splitlines()[1:] == [
            'I2 never-run',
            f'I1 retired by lead (fallback): {WHY}',
        ]

    async def test_only_retired_commands_do_not_read_as_empty(self, harness: RetireHarness) -> None:
        view_of(await harness.retire(approved_by='lead'))
        view_of(await harness.retire(id='I2', approved_by='lead'))

        view = await harness.status()

        assert view['commands'] == []
        assert 'no matching commands' not in view['text']
        assert len(view['retired']) == 2
