import inspect
import json
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

import pytest
from mcp.types import CallToolResult
from mightymodels_plugin.server import SERVER_NAME, TOOLS, AppState
from mightymodels_plugin.tools.contract.service import ContractService
from mightymodels_plugin.tools.protocol import ActionTool, LifespanState
from mightymodels_plugin.tools.review.service import ReviewService
from mightymodels_plugin.tools.task.service import TaskService
from mightymodels_plugin.tools.tests.support import (
    ActivityKind,
    DatabaseActivity,
    StateServer,
    ToolCall,
    text_of,
    tree,
)
from mightymodels_plugin.tools.ticket.service import TicketService

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


def ticket_results(server: StateServer, *calls: ToolCall) -> list[CallToolResult]:
    return server.call(*((name, {'slug': SLUG, **arguments}) for name, arguments in calls))


def served_actions(registered: Callable[..., object]) -> type[StrEnum]:
    return inspect.signature(registered).parameters['action'].annotation


class TestStateServer:
    def test_is_named_state(self, state_server: StateServer) -> None:
        assert state_server.name() == SERVER_NAME == 'state'

    def test_lists_its_tools_through_the_in_memory_client(self, state_server: StateServer) -> None:
        assert sorted(state_server.tools()) == ['contract', 'review', 'task', 'ticket']

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
        self, name: str, arguments: list[str], required: list[str], state_server: StateServer
    ) -> None:
        schema = state_server.tools()[name].input_schema

        assert list(schema['properties']) == arguments
        assert schema['required'] == required

    def test_review_offers_the_seven_actions(self, state_server: StateServer) -> None:
        schema = state_server.tools()['review'].input_schema

        assert schema['$defs']['ReviewAction']['enum'] == [
            'start',
            'add',
            'gate',
            'dispose',
            'resolve',
            'report',
            'list',
        ]

    def test_each_tool_is_described_by_its_docstring(self, state_server: StateServer) -> None:
        listed = state_server.tools()

        assert {name: tool.description for name, tool in listed.items()} == {
            tool.__name__: tool.__doc__ for tool in TOOLS
        }


class TestToolSchemas:
    SNAPSHOT = Path(__file__).parent.joinpath('fixtures', 'tool-schemas.json')

    @pytest.fixture
    def served_schemas(self, state_server: StateServer) -> dict[str, dict[str, object]]:
        return {
            name: {
                'description': tool.description,
                'input_schema': tool.input_schema,
                'output_schema': tool.output_schema,
            }
            for name, tool in state_server.tools().items()
        }

    def test_each_tool_schema_equals_the_snapshot_taken_before_the_rework(
        self, served_schemas: dict[str, dict[str, object]]
    ) -> None:
        assert served_schemas == json.loads(self.SNAPSHOT.read_text(encoding='utf-8'))


class TestToolProtocol:
    @pytest.fixture
    def app_state(
        self,
        ticket_service: TicketService,
        task_service: TaskService,
        contract_service: ContractService,
        review_service: ReviewService,
    ) -> AppState:
        return AppState(
            tickets=ticket_service,
            tasks=task_service,
            contracts=contract_service,
            reviews=review_service,
        )

    @pytest.mark.parametrize(
        'tool', [pytest.param(tool.__self__, id=tool.__name__) for tool in TOOLS]
    )
    def test_each_registered_tool_satisfies_the_action_tool_protocol(self, tool: object) -> None:
        assert isinstance(tool, ActionTool)

    @pytest.mark.parametrize(
        ('tool', 'actions'),
        [pytest.param(tool.__self__, served_actions(tool), id=tool.__name__) for tool in TOOLS],
    )
    def test_each_tool_handlers_cover_its_whole_action_enum(
        self, tool: ActionTool[StrEnum, object, object, object], actions: type[StrEnum]
    ) -> None:
        assert set(tool.handlers) == set(actions)

    def test_the_lifespan_state_satisfies_what_the_tools_resolve(self, app_state: AppState) -> None:
        assert isinstance(app_state, LifespanState)


class TestLifespanState:
    @pytest.fixture
    def activity_of_a_file_write_and_two_database_calls(
        self, state_server: StateServer, database_activity: DatabaseActivity
    ) -> DatabaseActivity:
        ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'validate'}),
            ('ticket', {'action': 'show'}),
        )
        return database_activity

    def test_one_engine_serves_every_call_and_is_disposed_when_the_client_closes(
        self, activity_of_a_file_write_and_two_database_calls: DatabaseActivity
    ) -> None:
        assert activity_of_a_file_write_and_two_database_calls.kinds() == [
            ActivityKind.TRANSACTION_OPENED,
            ActivityKind.TRANSACTION_OPENED,
            ActivityKind.ENGINE_DISPOSED,
        ]
        assert len(activity_of_a_file_write_and_two_database_calls.engines()) == 1


class TestOutsideARepository:
    @pytest.fixture
    def state_server(self, tmp_path: Path) -> StateServer:
        directory = tmp_path.joinpath('plain-directory')
        directory.mkdir()
        return StateServer(root=directory)

    def test_the_server_lists_its_tools_and_a_ticket_is_written_then_shown(
        self, state_server: StateServer
    ) -> None:
        listed = state_server.tools()
        written, _, shown = ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'validate'}),
            ('ticket', {'action': 'show'}),
        )

        assert sorted(listed) == ['contract', 'review', 'task', 'ticket']
        assert (written.is_error, shown.is_error) == (False, False)
        assert shown.structured_content['unit']['slug'] == SLUG
        assert not state_server.root.joinpath('.git').exists()


class TestToolCalls:
    def test_a_ticket_is_written_validated_and_read_back(self, state_server: StateServer) -> None:
        written, validated, shown = ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'validate'}),
            ('ticket', {'action': 'show'}),
        )

        assert state_server.root.joinpath('.mightymodels', SLUG, 'ticket.yml').is_file()
        assert written.structured_content == {
            'text': f'wrote .mightymodels/{SLUG}/ticket.yml; review it, then run validate\n',
            'unit': None,
        }
        assert validated.structured_content['unit']['ticket']['models']['architect'] == 'opus'
        assert shown.structured_content['unit'] == validated.structured_content['unit']

    def test_a_staged_ticket_takes_a_contract_and_a_task(self, state_server: StateServer) -> None:
        *_, approved, started, ready, status = ticket_results(
            state_server,
            ('ticket', {'action': 'write', 'fields': ANSWERS}),
            ('ticket', {'action': 'validate'}),
            ('contract', {'action': 'approve', 'commands': [COMMAND]}),
            ('task', {'action': 'start', 'task_id': 'T1', 'change': START}),
            ('task', {'action': 'ready'}),
            ('contract', {'action': 'status'}),
        )

        assert approved.structured_content['text'] == 'contract: 1 commands (1 new)\n'
        assert started.structured_content['tasks'][0]['attempts'] == {'engineer': 1}
        assert (ready.is_error, ready.structured_content['advanced']) == (False, False)
        assert status.structured_content['commands'] == [
            {'id': 'T1.AC-1', 'argv': ['true'], 'state': 'never-run'}
        ]

    def test_an_anticipated_failure_reaches_the_model_as_its_own_text(
        self, state_server: StateServer
    ) -> None:
        (shown,) = ticket_results(state_server, ('ticket', {'action': 'show'}))

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
        self, name: str, arguments: dict[str, object], needs: str, state_server: StateServer
    ) -> None:
        (result,) = ticket_results(state_server, (name, arguments))

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
        self,
        name: str,
        arguments: dict[str, object],
        connected_server: StateServer,
        tree_after_the_connect: dict[str, bytes],
        database_activity: DatabaseActivity,
    ) -> None:
        (result,) = ticket_results(connected_server, (name, arguments))

        assert result.is_error
        assert ActivityKind.TRANSACTION_OPENED not in database_activity.kinds()
        assert tree(connected_server.root) == tree_after_the_connect
