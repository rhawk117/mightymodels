from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import anyio
import pytest
from mcp import Client
from mcp.types import ToolAnnotations
from mightymodels_core.edge import OpenState
from mightymodels_core.primitives import TaskId
from mightymodels_core.tasks import Attempt, Transition
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.server.entrypoint import create_catalog
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.task.use_cases import create_task_work

from tests.mcp.ticket.e2e.test_ticket_tools import ANSWERED, SLUG, TicketHarness, view_of

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from _pytest.mark import ParameterSet
    from mcp.types import CallToolResult
    from mightymodels_core.git import Checkout, Git, GitRefusal, UntrackedFiles
    from mightymodels_mcp.server.icons import IconName
    from mightymodels_mcp.server.state import StateOpener

    from tests.mcp.server.server_harness import ServerHarness

WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
MARKS = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)
OWNED = 'src/a.py'
START = {
    'slug': SLUG,
    'task_id': 'R1',
    'by': 'engineer',
    'owned': [OWNED],
    'acceptance': ['AC-1'],
}
KEY = {'slug': SLUG, 'task_id': 'R1'}
SHORT = 12


@dataclass(slots=True, kw_only=True)
class RecordingGit:
    inner: Git
    asked: list[str] = field(default_factory=list)

    async def refusal(self) -> GitRefusal | None:
        self.asked.append('refusal')
        return await self.inner.refusal()

    async def checkout(self) -> Checkout | GitRefusal:
        self.asked.append('checkout')
        return await self.inner.checkout()

    async def common_directory(self) -> Path | None:
        self.asked.append('common_directory')
        return await self.inner.common_directory()

    async def resolve_head(self) -> str | None:
        self.asked.append('resolve_head')
        return await self.inner.resolve_head()

    async def resolve_commit(self, revision: str) -> str | None:
        self.asked.append('resolve_commit')
        return await self.inner.resolve_commit(revision)

    async def is_ancestor(self, base: str, commit: str) -> bool:
        self.asked.append('is_ancestor')
        return await self.inner.is_ancestor(base, commit)

    async def changed_files(self, base: str, commit: str) -> set[str]:
        self.asked.append('changed_files')
        return await self.inner.changed_files(base, commit)

    async def current_branch(self) -> str | None:
        self.asked.append('current_branch')
        return await self.inner.current_branch()

    async def dirty_paths(self, *, untracked: UntrackedFiles) -> list[str] | None:
        self.asked.append('dirty_paths')
        return await self.inner.dirty_paths(untracked=untracked)

    async def commits_on_no_remote(self, branch: str) -> int | None:
        self.asked.append('commits_on_no_remote')
        return await self.inner.commits_on_no_remote(branch)


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordingOpener:
    inner: StateOpener
    git_calls: list[str] = field(default_factory=list)

    @asynccontextmanager
    async def open(self) -> AsyncGenerator[OpenState]:
        async with self.inner.open() as state:
            recording = RecordingGit(inner=state.git, asked=self.git_calls)
            yield OpenState(checkout=state.checkout, git=recording, database=state.database)


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskHarness:
    server: ServerHarness
    opener: RecordingOpener

    @property
    def git_calls(self) -> list[str]:
        return self.opener.git_calls

    async def call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        self.git_calls.clear()
        server = create_server(ServerDependencies(state=self.opener), create_catalog())
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    async def git(self, *arguments: str) -> str:
        identity = ['-c', 'user.name=probe', '-c', 'user.email=probe@example.com']
        command = ['git', '-C', str(self.server.repository), *identity, *arguments]
        finished = await anyio.run_process(command)
        return finished.stdout.decode().strip()

    async def commit(self, message: str) -> str:
        await self.git('commit', '--allow-empty', '--quiet', '-m', message)
        return await self.git('rev-parse', 'HEAD')

    async def verify_plan_task(self) -> None:
        moment = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
        verified = Transition(
            task_key=TaskId('T1'),
            before='pending',
            after='verified',
            reasons=(),
            head=None,
            at=moment,
        )
        attempt = Attempt(worker='engineer', mode=None, owned=())
        async with self.opener.open() as state:
            with create_task_work(state).write() as unit:
                ticket_id = unit.tasks.tickets.staged_ticket(SLUG).id
                unit.tasks.tasks.record_start(ticket_id, verified, attempt)

    async def commit_owned_file(self) -> str:
        path = anyio.Path(self.server.repository, OWNED)
        await path.parent.mkdir(parents=True, exist_ok=True)
        await path.write_text('changed\n')
        await self.git('add', OWNED)
        return await self.commit('change the owned file')


def listed_tool_cases() -> pytest.MarkDecorator:
    tools: list[ParameterSet] = [
        pytest.param('task_start', 'Start a task', WRITES, 'task', id='start'),
        pytest.param('task_verify', 'Verify a task', WRITES, 'task', id='verify'),
        pytest.param('task_mark', 'Mark a task', MARKS, 'task', id='mark'),
        pytest.param('task_show', 'Show the tasks', READS, 'task', id='show'),
        pytest.param('task_ready', 'Check the tasks are ready', READS, 'task', id='ready'),
        pytest.param(
            'failed_fix_record', 'Record a failed fix', WRITES, 'failed_fix', id='failed-fix'
        ),
    ]
    return pytest.mark.parametrize(('name', 'title', 'annotations', 'icon'), tools)


@pytest.fixture
async def staged(server_harness: ServerHarness) -> TaskHarness:
    tickets = TicketHarness(server=server_harness)
    view_of(await tickets.call('ticket_write', dict(ANSWERED)))
    view_of(await tickets.call('ticket_validate', {'slug': SLUG}))
    opener = RecordingOpener(inner=server_harness.dependencies.state)
    return TaskHarness(server=server_harness, opener=opener)


@pytest.fixture
async def started(staged: TaskHarness) -> TaskHarness:
    await staged.commit('first')
    view_of(await staged.call('task_start', START))
    return staged


class TestListedTools:
    @listed_tool_cases()
    async def test_tool_carries_title_hints_and_icon(
        self,
        server_harness: ServerHarness,
        name: str,
        title: str,
        annotations: ToolAnnotations,
        icon: IconName,
    ) -> None:
        server = server_harness.create_server(create_catalog())
        async with Client(server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}

        tool = listed[name]
        assert (tool.title, tool.annotations) == (title, annotations)
        assert tool.icons == [load_icon(icon)]


class TestTaskStart:
    async def test_start_records_the_task_from_head(self, staged: TaskHarness) -> None:
        head = await staged.commit('first')

        view = view_of(await staged.call('task_start', START))

        assert view['text'] == f'R1 in-progress by engineer from {head[:SHORT]}\n'
        assert view['advanced']
        assert view['tasks'] == [
            {
                'id': 'R1',
                'status': 'in-progress',
                'owned': [OWNED],
                'base': head,
                'commit': None,
                'attempts': {'engineer': 1},
                'reasons': [],
            }
        ]
        assert staged.git_calls == ['resolve_head']

    async def test_start_without_a_commit_names_an_unknown_head(self, staged: TaskHarness) -> None:
        view = view_of(await staged.call('task_start', START))

        assert view['text'] == 'R1 in-progress by engineer from unknown\n'

    async def test_starting_a_task_already_underway_is_refused(self, started: TaskHarness) -> None:
        assert (await started.call('task_start', START)).is_error


class TestTaskShow:
    async def test_unstarted_ticket_has_no_tasks(self, staged: TaskHarness) -> None:
        view = view_of(await staged.call('task_show', {'slug': SLUG}))

        assert view['text'] == 'no tasks started\n'
        assert view['advanced']
        assert staged.git_calls == []

    async def test_lists_each_task_with_its_attempts(self, started: TaskHarness) -> None:
        view = view_of(await started.call('task_show', {'slug': SLUG}))

        assert view['text'] == "R1\tin-progress\tattempts {'engineer': 1}\t\n"
        assert started.git_calls == []

    async def test_unstaged_ticket_is_refused(self, server_harness: ServerHarness) -> None:
        opener = RecordingOpener(inner=server_harness.dependencies.state)
        harness = TaskHarness(server=server_harness, opener=opener)

        assert (await harness.call('task_show', {'slug': SLUG})).is_error


class TestTaskVerify:
    async def test_verifies_the_head_commit_within_the_owned_set(
        self, started: TaskHarness
    ) -> None:
        head = await started.commit_owned_file()
        arguments = {**KEY, 'commit': head, 'assertions': {'AC-1': 'seen in the diff'}}

        view = view_of(await started.call('task_verify', arguments))

        assert view['text'] == 'R1 verified\n'
        assert view['advanced']
        assert view['tasks'][0]['commit'] == head
        assert 'resolve_head' in started.git_calls

    async def test_blocked_verification_lists_the_problems(self, started: TaskHarness) -> None:
        base = await started.git('rev-parse', 'HEAD')
        await started.commit_owned_file()
        arguments = {**KEY, 'commit': base, 'assertions': {'AC-1': 'seen in the diff'}}

        view = view_of(await started.call('task_verify', arguments))

        problem = 'the reported commit must resolve to the current HEAD'
        assert view['text'] == f'R1 blocked\n  - {problem}\n'
        assert not view['advanced']

    async def test_unstarted_task_is_refused_before_git_is_asked(self, staged: TaskHarness) -> None:
        result = await staged.call('task_verify', {**KEY, 'commit': 'HEAD'})

        assert result.is_error
        assert staged.git_calls == []


class TestTaskMark:
    async def test_marks_the_task_without_asking_git(self, started: TaskHarness) -> None:
        arguments = {**KEY, 'to': 'superseded', 'reason': 'replaced by R2'}

        view = view_of(await started.call('task_mark', arguments))

        assert view['text'] == 'R1 superseded: replaced by R2\n'
        assert view['advanced']
        assert view['tasks'][0]['status'] == 'superseded'
        assert started.git_calls == []

    async def test_unknown_task_is_refused(self, staged: TaskHarness) -> None:
        arguments = {**KEY, 'to': 'failed', 'reason': 'never started'}

        assert (await staged.call('task_mark', arguments)).is_error
        assert staged.git_calls == []


class TestTaskReady:
    async def test_unverified_plan_task_is_not_ready(self, staged: TaskHarness) -> None:
        await staged.commit('first')
        view_of(await staged.call('task_start', {**START, 'task_id': 'T1'}))

        view = view_of(await staged.call('task_ready', {'slug': SLUG}))

        assert view['text'] == 'not ready\n  - T1 is in-progress, not verified\n'
        assert not view['advanced']
        assert staged.git_calls == ['resolve_head']

    async def test_verified_plan_task_is_ready_at_head(self, staged: TaskHarness) -> None:
        head = await staged.commit('first')
        await staged.verify_plan_task()

        view = view_of(await staged.call('task_ready', {'slug': SLUG}))

        assert view['text'] == f'ready at {head[:SHORT]}\n'
        assert view['advanced']
        assert staged.git_calls == ['resolve_head']


class TestFailedFixRecord:
    async def test_records_the_fix_and_the_fixes_left(self, started: TaskHarness) -> None:
        view = view_of(await started.call('failed_fix_record', {**KEY, 'hypothesis': 'the cache'}))

        assert view['text'] == 'R1 failed fix 1 recorded: the cache\n2 left\n'
        assert not view['advanced']
        assert started.git_calls == []

    async def test_a_fourth_fix_is_refused(self, started: TaskHarness) -> None:
        for number in range(3):
            arguments = {**KEY, 'hypothesis': f'guess {number}'}
            view_of(await started.call('failed_fix_record', arguments))

        result = await started.call('failed_fix_record', {**KEY, 'hypothesis': 'one more'})

        assert result.is_error
        assert started.git_calls == []

    async def test_unstarted_task_is_refused(self, staged: TaskHarness) -> None:
        result = await staged.call('failed_fix_record', {**KEY, 'hypothesis': 'early'})

        assert result.is_error
