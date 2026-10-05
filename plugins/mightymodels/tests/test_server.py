import asyncio
from pathlib import Path

import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent, Tool
from mightymodels_plugin.server import SERVER_NAME, TOOLS, build_server

SLUG = 'retry-queue'
ANSWERS = {
    'summary': 'Retry queue drains slowly',
    'scope': 'large',
    'compaction': True,
    'branch': 'fix/retry-queue',
    'context': ['drain loop sleeps between batches'],
}
COMMAND = {'id': 'T1.AC-1', 'argv': ['true'], 'approved_by': 'user'}
START = {'by': 'engineer', 'owned': ['src/queue.py']}


async def list_tools() -> dict[str, Tool]:
    async with Client(build_server()) as client:
        result = await client.list_tools()
    return {tool.name: tool for tool in result.tools}


async def read_server_name() -> str | None:
    async with Client(build_server()) as client:
        return client.server_info.name if client.server_info else None


async def call_tools(*calls: tuple[str, dict[str, object]]) -> list[CallToolResult]:
    async with Client(build_server()) as client:
        return [
            await client.call_tool(name, {'slug': SLUG, **arguments}) for name, arguments in calls
        ]


def text_of(result: CallToolResult) -> str:
    return ''.join(block.text for block in result.content if isinstance(block, TextContent))


class TestStateServer:
    def test_is_named_state(self) -> None:
        assert asyncio.run(read_server_name()) == SERVER_NAME == 'state'

    def test_lists_its_tools_through_the_in_memory_client(self) -> None:
        assert sorted(asyncio.run(list_tools())) == ['contract', 'review', 'task', 'ticket']

    @pytest.mark.parametrize(
        ('name', 'arguments', 'required'),
        [
            pytest.param('ticket', ['action', 'slug', 'fields'], ['action', 'slug'], id='ticket'),
            pytest.param(
                'task', ['action', 'slug', 'task_id', 'change'], ['action', 'slug'], id='task'
            ),
            pytest.param(
                'contract', ['action', 'slug', 'commands'], ['action', 'slug'], id='contract'
            ),
            pytest.param('review', ['action', 'run_id', 'payload'], ['action'], id='review'),
        ],
    )
    def test_each_tool_takes_the_arguments_the_surface_gives_it(
        self, name: str, arguments: list[str], required: list[str]
    ) -> None:
        schema = asyncio.run(list_tools())[name].input_schema

        assert list(schema['properties']) == arguments
        assert schema['required'] == required

    def test_review_offers_the_seven_actions(self) -> None:
        schema = asyncio.run(list_tools())['review'].input_schema

        assert schema['$defs']['ReviewAction']['enum'] == [
            'start',
            'add',
            'gate',
            'dispose',
            'resolve',
            'report',
            'list',
        ]

    def test_each_tool_is_described_by_its_docstring(self) -> None:
        listed = asyncio.run(list_tools())

        assert {name: tool.description for name, tool in listed.items()} == {
            tool.__name__: tool.__doc__ for tool in TOOLS
        }


@pytest.mark.usefixtures('project')
class TestToolCalls:
    @pytest.fixture
    def project(self, repository: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(repository))
        return repository

    def test_a_ticket_is_written_validated_and_read_back(self, project: Path) -> None:
        written, validated, shown = asyncio.run(
            call_tools(
                ('ticket', {'action': 'write', 'fields': ANSWERS}),
                ('ticket', {'action': 'validate'}),
                ('ticket', {'action': 'show'}),
            )
        )

        assert project.joinpath('.mightymodels', SLUG, 'ticket.yml').is_file()
        assert written.structured_content == {
            'text': f'wrote .mightymodels/{SLUG}/ticket.yml; review it, then run validate\n',
            'unit': None,
        }
        assert validated.structured_content['unit']['ticket']['models']['architect'] == 'opus'
        assert shown.structured_content['unit'] == validated.structured_content['unit']

    def test_a_staged_ticket_takes_a_contract_and_a_task(self) -> None:
        *_, approved, started, ready, status = asyncio.run(
            call_tools(
                ('ticket', {'action': 'write', 'fields': ANSWERS}),
                ('ticket', {'action': 'validate'}),
                ('contract', {'action': 'approve', 'commands': [COMMAND]}),
                ('task', {'action': 'start', 'task_id': 'T1', 'change': START}),
                ('task', {'action': 'ready'}),
                ('contract', {'action': 'status'}),
            )
        )

        assert approved.structured_content['text'] == 'contract: 1 commands (1 new)\n'
        assert started.structured_content['tasks'][0]['attempts'] == {'engineer': 1}
        assert (ready.is_error, ready.structured_content['advanced']) == (False, False)
        assert status.structured_content['commands'] == [
            {'id': 'T1.AC-1', 'argv': ['true'], 'state': 'never-run'}
        ]

    def test_an_anticipated_failure_reaches_the_model_as_its_own_text(self) -> None:
        (shown,) = asyncio.run(call_tools(('ticket', {'action': 'show'})))

        assert shown.is_error
        assert f'{SLUG} is not staged; stage the ticket with open-ticket first' in text_of(shown)

    @pytest.mark.parametrize(
        ('name', 'arguments', 'needs'),
        [
            pytest.param('ticket', {'action': 'write'}, 'write needs fields', id='write'),
            pytest.param(
                'ticket',
                {'action': 'update-context', 'fields': ANSWERS},
                'update-context needs fields holding only the context lines',
                id='update-context',
            ),
            pytest.param('task', {'action': 'start', 'task_id': 'T1'}, 'start needs', id='start'),
            pytest.param(
                'task', {'action': 'verify', 'change': START}, 'verify needs', id='verify'
            ),
            pytest.param('task', {'action': 'mark', 'task_id': 'T1'}, 'mark needs', id='mark'),
            pytest.param('contract', {'action': 'approve'}, 'approve needs', id='approve'),
        ],
    )
    def test_an_action_missing_its_arguments_says_what_it_needs(
        self, name: str, arguments: dict[str, object], needs: str
    ) -> None:
        (result,) = asyncio.run(call_tools((name, arguments)))

        assert result.is_error
        assert needs in text_of(result)

    @pytest.mark.parametrize(
        ('name', 'arguments'),
        [
            pytest.param(
                'task', {'action': 'start', 'task_id': 'X1', 'change': START}, id='task-id'
            ),
            pytest.param(
                'task',
                {'action': 'mark', 'task_id': 'T1', 'change': {'to': 'verified', 'reason': 'r'}},
                id='mark-verified',
            ),
            pytest.param('ticket', {'action': 'delete'}, id='unknown-action'),
        ],
    )
    def test_arguments_outside_the_schema_are_refused(
        self, name: str, arguments: dict[str, object], project: Path
    ) -> None:
        (result,) = asyncio.run(call_tools((name, arguments)))

        assert result.is_error
        assert not project.joinpath('.mightymodels').exists()
