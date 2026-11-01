"""The contract flow through the launcher's real server over stdio against a real git repository."""

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from mcp import Client
from mightymodels_core.tasks.gates import NO_LANDING_COMMAND

from tests.core.git.git_builders import commit_file, run_git
from tests.mcp.server.integration.launch_builder import (
    SERVER_NAME,
    create_launch_parameters,
    load_declared_servers,
)
from tests.mcp.server.server_harness import view_of
from tests.mcp.ticket.ticket_harness import ANSWERED, SLUG

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from tests.mcp.server.server_harness import ServerHarness

OWNED = 'owned.txt'
APPROVER = 'lead'
PROBE = (
    'import os; print(os.getcwd());'
    ' [print(name, name in os.environ) for name in'
    ' ("UV_PROJECT", "UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV")]'
)
SILENT_SECONDS = 32


def integration_command() -> dict[str, Any]:
    return {'id': 'I1', 'argv': (sys.executable, '-c', PROBE), 'approved_by': APPROVER}


def landing_command() -> dict[str, Any]:
    argv = (sys.executable, '-c', 'print("landed")')
    return {'id': 'L1', 'argv': argv, 'approved_by': APPROVER}


def silent_command() -> dict[str, Any]:
    return {
        'id': 'I1',
        'argv': (sys.executable, '-c', f'import time; time.sleep({SILENT_SECONDS})'),
        'timeout': 120,
        'approved_by': APPROVER,
    }


@dataclass(slots=True, kw_only=True)
class ProgressLog:
    notes: list[tuple[float, str | None]] = field(default_factory=list)

    async def record(self, progress: float, total: float | None, message: str | None) -> None:
        assert total is None
        self.notes.append((progress, message))


@dataclass(slots=True, kw_only=True, frozen=True)
class Flow:
    client: Client
    repository: Path

    async def call(
        self, name: str, arguments: dict[str, Any], log: ProgressLog | None = None
    ) -> dict[str, Any]:
        callback = log.record if log else None
        result = await self.client.call_tool(name, arguments, progress_callback=callback)
        return view_of(result)

    async def approve(self, *commands: dict[str, Any]) -> None:
        await self.call('contract_approve', {'slug': SLUG, 'commands': list(commands)})

    async def run(self, phase: str, log: ProgressLog | None = None, *ids: str) -> dict[str, Any]:
        arguments = {'slug': SLUG, 'phase': phase, **({'ids': list(ids)} if ids else {})}
        return await self.call('contract_run', arguments, log)

    async def ready(self) -> str:
        return (await self.call('task_ready', {'slug': SLUG}))['text']

    async def head(self) -> str:
        return await run_git(self.repository, 'rev-parse', 'HEAD')

    async def start_and_verify_task(self) -> None:
        base = await self.head()
        start = {
            'slug': SLUG,
            'task_id': 'T1',
            'by': 'engineer',
            'owned': [OWNED],
            'acceptance': ['AC-1'],
        }
        await self.call('task_start', start)
        head = await commit_file(self.repository, OWNED)
        brief = self.repository.joinpath('.mightymodels', SLUG, 'briefs', 'task-01.md')
        brief.parent.mkdir(parents=True)
        brief.write_text(
            f'## ASKED\n  - AC-1: changed\n## DONE\ncommit: {head}\n', encoding='utf-8'
        )
        verify = {'slug': SLUG, 'task_id': 'T1', 'commit': head, 'assertions': {'AC-1': 'seen'}}
        view = await self.call('task_verify', verify)
        assert view['text'] == 'T1 verified\n', (base, view['text'])


@pytest.fixture(scope='module')
def environment_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('launcher').joinpath('venv')


@pytest.fixture
async def flow(server_harness: ServerHarness, environment_directory: Path) -> AsyncIterator[Flow]:
    parameters = create_launch_parameters(
        declared=load_declared_servers()[SERVER_NAME],
        server_harness=server_harness,
        environment_directory=environment_directory,
    )
    repository = server_harness.repository
    async with Client(parameters) as client:
        created = Flow(client=client, repository=repository)
        await created.call('ticket_write', dict(ANSWERED))
        await created.call('ticket_validate', {'slug': SLUG})
        await created.call('task_declare', {'slug': SLUG, 'task_ids': ['T1']})
        await commit_file(repository, 'base.txt')
        yield created


class TestLandingFlow:
    async def test_readiness_lifts_only_after_a_pass_at_head(self, flow: Flow) -> None:
        await flow.approve(integration_command(), landing_command())
        await flow.start_and_verify_task()
        head = await flow.head()

        before = await flow.ready()
        assert before.startswith('not ready')
        assert 'I1 has no receipt at the current HEAD' in before
        assert 'L1 has no receipt at the current HEAD' in before

        await flow.run('task', None, 'I1')
        partial = await flow.ready()
        assert 'L1 has no receipt at the current HEAD' in partial
        assert 'I1 has no receipt' not in partial

        await flow.run('landing', None, 'L1')
        assert await flow.ready() == f'ready at {head[:12]}\n'

        await commit_file(flow.repository, 'later.txt')
        moved = await flow.ready()
        assert moved.startswith('not ready')
        assert 'no receipt at the current HEAD' in moved

        await flow.run('landing', None, 'L1')
        assert 'I1 has no receipt at the current HEAD' in await flow.ready()

        await flow.run('task', None, 'I1')
        assert (await flow.ready()).startswith('ready at ')

    async def test_child_runs_in_the_target_repository_without_the_launcher_variables(
        self, flow: Flow
    ) -> None:
        await flow.approve(integration_command(), landing_command())

        view = await flow.run('task')

        row = next(row for row in view['receipts'] if row['id'] == 'I1')
        assert row['outcome'] == 'pass'
        assert row['stdout_tail'].splitlines() == [
            str(flow.repository),
            'UV_PROJECT False',
            'UV_PROJECT_ENVIRONMENT False',
            'VIRTUAL_ENV False',
        ]

    async def test_a_passing_integration_command_alone_is_not_ready(self, flow: Flow) -> None:
        await flow.approve(integration_command())
        await flow.start_and_verify_task()
        await flow.run('task')

        text = await flow.ready()

        assert text == f'not ready\n  - {NO_LANDING_COMMAND}\n'

    async def test_a_retired_command_stops_counting(self, flow: Flow) -> None:
        await flow.approve(integration_command(), landing_command())
        await flow.start_and_verify_task()
        await flow.run('landing', None, 'L1')
        assert 'I1 has no receipt' in await flow.ready()

        retire = {'slug': SLUG, 'id': 'I1', 'why': 'moved', 'approved_by': APPROVER}
        await flow.call('contract_retire', retire)

        assert (await flow.ready()).startswith('ready at ')


class TestHeartbeat:
    async def test_a_silent_command_still_reports_progress_while_it_runs(self, flow: Flow) -> None:
        await flow.approve(silent_command())
        log = ProgressLog()

        with anyio.fail_after(SILENT_SECONDS + 20):
            view = await flow.run('task', log)

        assert view['passing'] is True
        running = [
            (progress, message) for progress, message in log.notes if 'running' in str(message)
        ]
        assert len(running) >= 1
        positions = [progress for progress, _ in log.notes]
        assert positions == sorted(set(positions))
