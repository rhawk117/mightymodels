import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from mcp import Client
from mcp.types import ElicitRequestFormParams, ElicitResult
from mightymodels_core.contract.runs import RunProgress
from mightymodels_mcp.contract.tools import ToolProgressReporter
from mightymodels_mcp.main import create_catalog

from tests.mcp.server.server_harness import view_of
from tests.mcp.ticket.ticket_harness import ANSWERED, SLUG, TicketHarness

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mcp.client.session import ClientRequestContext
    from mcp.types import CallToolResult, ElicitRequestParams

    from tests.mcp.server.server_harness import ServerHarness

PHASES = ('planning', 'task', 'review', 'landing')
GIT_IDENTITY = ('-c', 'user.name=probe', '-c', 'user.email=probe@example.com')
PASSING = {'id': 'I1', 'argv': (sys.executable, '-c', 'print("one")')}
FAILING = {'id': 'I2', 'argv': (sys.executable, '-c', 'import sys; sys.exit(3)')}
LAST = {'id': 'I3', 'argv': (sys.executable, '-c', 'print("three")')}


@dataclass(slots=True, kw_only=True)
class ProgressLog:
    notes: list[tuple[float, str | None]] = field(default_factory=list)

    async def record(self, progress: float, total: float | None, message: str | None) -> None:
        assert total is None
        self.notes.append((progress, message))


async def approve_by_form(
    context: ClientRequestContext, params: ElicitRequestParams
) -> ElicitResult:
    assert context
    assert isinstance(params, ElicitRequestFormParams)
    return ElicitResult(action='accept', content={'approval': 'approve'})


@dataclass(slots=True, kw_only=True, frozen=True)
class RunHarness:
    tickets: TicketHarness

    async def call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        server = self.tickets.server.create_server(create_catalog())
        async with Client(server, elicitation_callback=approve_by_form) as client:
            return await client.call_tool(name, arguments)

    async def run(self, log: ProgressLog | None = None, **extra: Any) -> CallToolResult:
        arguments = {'slug': SLUG, 'phase': 'task', **extra}
        server = self.tickets.server.create_server(create_catalog())
        async with Client(server) as client:
            return await client.call_tool(
                'contract_run', arguments, progress_callback=log.record if log else None
            )

    async def approve(self, *commands: dict[str, Any]) -> None:
        view_of(await self.call('contract_approve', {'slug': SLUG, 'commands': list(commands)}))

    async def git(self, *arguments: str) -> None:
        repository = str(self.tickets.server.repository)
        await anyio.run_process(['git', '-C', repository, *GIT_IDENTITY, *arguments])


def refused_phase_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param({}, id='left-out'),
        pytest.param({'phase': 'someday'}, id='unknown'),
    ]
    return pytest.mark.parametrize('extra', cases)


@pytest.fixture
async def harness(server_harness: ServerHarness) -> RunHarness:
    tickets = TicketHarness(server=server_harness)
    created = RunHarness(tickets=tickets)
    view_of(await tickets.call('ticket_write', dict(ANSWERED)))
    view_of(await tickets.call('ticket_validate', {'slug': SLUG}))
    await created.git('commit', '--allow-empty', '--quiet', '-m', 'init')
    return created


class TestContractRun:
    async def test_every_live_command_gets_a_result_in_approved_order(
        self, harness: RunHarness
    ) -> None:
        await harness.approve(PASSING, LAST)

        view = view_of(await harness.run())

        assert [row['id'] for row in view['receipts']] == ['I1', 'I3']
        assert view['passing'] is True
        assert [row['outcome'] for row in view['receipts']] == ['pass', 'pass']
        assert len(view['text'].splitlines()) == 2

    async def test_failed_command_does_not_stop_the_run(self, harness: RunHarness) -> None:
        await harness.approve(PASSING, FAILING, LAST)

        view = view_of(await harness.run())

        assert [(row['id'], row['outcome']) for row in view['receipts']] == [
            ('I1', 'pass'),
            ('I2', 'fail'),
            ('I3', 'pass'),
        ]
        assert view['receipts'][1]['exit'] == 3
        assert view['passing'] is False

    async def test_ids_pick_the_commands_to_run(self, harness: RunHarness) -> None:
        await harness.approve(PASSING, LAST)

        view = view_of(await harness.run(ids=['I3']))

        assert [row['id'] for row in view['receipts']] == ['I3']

    async def test_progress_rises_and_names_each_command(self, harness: RunHarness) -> None:
        await harness.approve(PASSING, FAILING)
        log = ProgressLog()

        view_of(await harness.run(log))

        positions = [progress for progress, _ in log.notes]
        messages = [message or '' for _, message in log.notes]
        assert positions == sorted(set(positions))
        assert len(positions) >= 4
        assert any(message.startswith('I1 ') and '(1 of 2)' in message for message in messages)
        assert any(message.startswith('I2 ') and '(2 of 2)' in message for message in messages)
        assert 'I2 fail (2 of 2)' in messages

    @refused_phase_cases()
    async def test_phase_left_out_or_unknown_is_refused(
        self, harness: RunHarness, extra: dict[str, str]
    ) -> None:
        await harness.approve(PASSING)
        arguments = {'slug': SLUG, **extra}
        server = harness.tickets.server.create_server(create_catalog())

        async with Client(server) as client:
            result = await client.call_tool('contract_run', arguments)

        assert result.is_error

    @pytest.mark.parametrize('phase', PHASES)
    async def test_each_phase_is_accepted(self, harness: RunHarness, phase: str) -> None:
        await harness.approve(PASSING)

        view = view_of(await harness.run(phase=phase))

        assert view['passing'] is True

    async def test_task_shaped_id_is_refused(self, harness: RunHarness) -> None:
        await harness.approve(PASSING)

        result = await harness.run(ids=['T1.AC-1'])

        assert result.is_error
        assert 'T1.AC-1' in str(result.content)

    async def test_tracked_changes_are_refused(
        self, harness: RunHarness, server_harness: ServerHarness
    ) -> None:
        await harness.approve(PASSING)
        tracked = server_harness.repository.joinpath('tracked.txt')
        tracked.write_text('one\n', encoding='utf-8')
        await harness.git('add', 'tracked.txt')
        await harness.git('commit', '--quiet', '-m', 'track')
        tracked.write_text('two\n', encoding='utf-8')

        result = await harness.run()

        assert result.is_error
        assert 'tracked.txt' in str(result.content)

    async def test_receipt_reports_form_and_fallback_approval_sources(
        self, harness: RunHarness
    ) -> None:
        await harness.approve(PASSING)
        await harness.approve({**LAST, 'approved_by': 'lead'})

        view = view_of(await harness.run())

        assert [(row['id'], row['approval_source']) for row in view['receipts']] == [
            ('I1', 'form'),
            ('I3', 'fallback'),
        ]


@dataclass(slots=True, kw_only=True, frozen=True)
class GoneContext:
    error: Exception

    async def report_progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None:
        assert (progress, total, message) == (0, None, 'I1 running (1 of 1)')
        raise self.error


class TestToolProgressReporter:
    @pytest.mark.parametrize('error', [anyio.BrokenResourceError(), anyio.ClosedResourceError()])
    async def test_a_client_that_went_away_does_not_fail_the_report(self, error: Exception) -> None:
        reporter = ToolProgressReporter(ctx=GoneContext(error=error))
        progress = RunProgress(key='I1', position=1, total=1, state='running')

        await reporter.report(progress)

    async def test_any_other_failure_still_surfaces(self) -> None:
        context = GoneContext(error=RuntimeError('boom'))
        reporter = ToolProgressReporter(ctx=context)
        progress = RunProgress(key='I1', position=1, total=1, state='running')

        with pytest.raises(RuntimeError, match='boom'):
            await reporter.report(progress)
