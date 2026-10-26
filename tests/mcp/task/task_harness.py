"""The task tools' shared e2e fixtures: a git-recording state opener and a client harness."""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import anyio
from mightymodels_core.edge import OpenState
from mightymodels_core.primitives import TaskId
from mightymodels_core.tasks import Attempt, Transition
from mightymodels_mcp.main import create_catalog
from mightymodels_mcp.server.app import create_server
from mightymodels_mcp.server.dependencies import ServerDependencies
from mightymodels_mcp.task.use_cases import create_task_work

from mcp import Client
from tests.mcp.ticket.ticket_harness import SLUG

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from mcp.types import CallToolResult
    from mightymodels_core.git import Checkout, Git, GitRefusal, UntrackedFiles
    from mightymodels_mcp.server.state import StateOpener

    from tests.mcp.server.server_harness import ServerHarness

OWNED = 'src/a.py'


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
