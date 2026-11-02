from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.git import GitMissingError
from mightymodels_core.primitives import Slug, TaskId
from mightymodels_core.tasks.records import TaskRecord
from mightymodels_mcp.task.gate_facts import (
    VerificationSources,
    gather_verification,
)
from mightymodels_mcp.task.schemas import TaskVerifyRequest

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.git import Checkout, GitRefusal, UntrackedFiles
    from mightymodels_core.tasks import VerifyRequest

SLUG = Slug('probe')
HEAD = 'h' * 40
BASE = 'b' * 40
COMMIT = 'c' * 40
CHANGED = {'src/a.py'}


@dataclass(slots=True, kw_only=True)
class FakeGit:
    refused: GitRefusal | None = None
    resolving: dict[str, str] = field(default_factory=lambda: {'work': COMMIT, 'main': BASE})
    ancestor: bool = True
    asked: list[str] = field(default_factory=list)

    async def refusal(self) -> GitRefusal | None:
        self.asked.append('refusal')
        return self.refused

    async def checkout(self) -> Checkout | GitRefusal:
        raise NotImplementedError

    async def common_directory(self) -> Path | None:
        raise NotImplementedError

    async def is_ancestor(self, base: str, commit: str) -> bool:
        self.asked.append(f'ancestor {base} {commit}')
        return self.ancestor

    async def changed_files(self, base: str, commit: str) -> set[str]:
        self.asked.append(f'changed {base} {commit}')
        return set(CHANGED)

    async def resolve_head(self) -> str | None:
        self.asked.append('head')
        return HEAD

    async def resolve_commit(self, revision: str) -> str | None:
        self.asked.append(f'commit {revision}')
        return self.resolving.get(revision)

    async def current_branch(self) -> str | None:
        raise NotImplementedError

    async def dirty_paths(self, *, untracked: UntrackedFiles) -> list[str] | None:
        raise NotImplementedError

    async def commits_on_no_remote(self, branch: str) -> int | None:
        raise NotImplementedError


def create_seen(key: str = 'T3', base: str | None = 'main') -> TaskRecord:
    return TaskRecord(key=TaskId(key), status='in-progress', owned=('src/a.py',), base=base)


def create_request(key: str = 'T3', commit: str = 'work') -> TaskVerifyRequest:
    return TaskVerifyRequest(
        slug=SLUG, task_id=TaskId(key), commit=commit, verdict='failed', reason='a test fails'
    )


async def gather(git: FakeGit, seen: TaskRecord, request: TaskVerifyRequest) -> VerifyRequest:
    return await gather_verification(VerificationSources(git=git), seen, request)


class TestGatherVerification:
    async def test_refusal_is_raised_before_anything_else_is_asked(self) -> None:
        git = FakeGit(refused=GitMissingError())

        with pytest.raises(GitMissingError):
            await gather(git, create_seen(), create_request())

        assert git.asked == ['refusal']

    async def test_facts_come_from_git(self) -> None:
        verify = await gather(FakeGit(), create_seen('R1'), create_request('R1'))

        assert (verify.commit, verify.verdict, verify.reason) == (COMMIT, 'failed', 'a test fails')
        assert (verify.git.head, verify.git.base_resolves, verify.git.base_is_ancestor) == (
            HEAD,
            True,
            True,
        )
        assert verify.git.changed_files == CHANGED

    async def test_unresolved_commit_keeps_the_request_text(self) -> None:
        git = FakeGit()

        verify = await gather(git, create_seen('R1'), create_request('R1', 'nowhere'))

        assert verify.commit == 'nowhere'
        assert verify.git.base_resolves
        assert not verify.git.base_is_ancestor
        assert verify.git.changed_files == frozenset()
        assert not any(asked.startswith(('ancestor', 'changed')) for asked in git.asked)

    @pytest.mark.parametrize('seen', [create_seen('R1', base=None), create_seen('R1', base='gone')])
    async def test_unresolved_base_asks_no_comparison(self, seen: TaskRecord) -> None:
        git = FakeGit()

        verify = await gather(git, seen, create_request('R1'))

        assert not verify.git.base_resolves
        assert (verify.git.base_is_ancestor, verify.git.changed_files) == (False, frozenset())
        assert not any(asked.startswith(('ancestor', 'changed')) for asked in git.asked)

    async def test_base_not_an_ancestor_is_reported(self) -> None:
        verify = await gather(FakeGit(ancestor=False), create_seen('R1'), create_request('R1'))

        assert not verify.git.base_is_ancestor
