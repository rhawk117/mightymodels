from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.git import GitMissingError
from mightymodels_core.primitives import Slug, TaskId
from mightymodels_core.tasks import Brief
from mightymodels_core.tasks.records import TaskRecord
from mightymodels_core.workspace import workspace_of
from mightymodels_mcp.task.gate_facts import (
    VerificationSources,
    gather_verification,
    load_brief,
    resolve_named_commit,
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
NAMED = 'd' * 40
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
        slug=SLUG, task_id=TaskId(key), commit=commit, assertions={'AC-1': 'ok'}
    )


def write_brief(root: Path, number: int, text: str) -> None:
    brief = workspace_of(root).task_brief(SLUG, number)
    brief.parent.mkdir(parents=True)
    brief.write_text(text, encoding='utf-8')


async def gather(
    git: FakeGit, root: Path, seen: TaskRecord, request: TaskVerifyRequest
) -> VerifyRequest:
    return await gather_verification(
        VerificationSources(git=git, workspace=workspace_of(root)), seen, request
    )


class TestGatherVerification:
    async def test_refusal_is_raised_before_anything_else_is_asked(self, tmp_path: Path) -> None:
        git = FakeGit(refused=GitMissingError())

        with pytest.raises(GitMissingError):
            await gather(git, tmp_path, create_seen(), create_request())

        assert git.asked == ['refusal']

    async def test_facts_come_from_git(self, tmp_path: Path) -> None:
        verify = await gather(FakeGit(), tmp_path, create_seen('R1'), create_request('R1'))

        assert (verify.commit, verify.assertions) == (COMMIT, {'AC-1': 'ok'})
        assert (verify.git.head, verify.git.base_resolves, verify.git.base_is_ancestor) == (
            HEAD,
            True,
            True,
        )
        assert verify.git.changed_files == CHANGED
        assert (verify.brief, verify.git.named_commit) == (None, None)

    async def test_unresolved_commit_keeps_the_request_text(self, tmp_path: Path) -> None:
        git = FakeGit()

        verify = await gather(git, tmp_path, create_seen('R1'), create_request('R1', 'nowhere'))

        assert verify.commit == 'nowhere'
        assert verify.git.base_resolves
        assert not verify.git.base_is_ancestor
        assert verify.git.changed_files == frozenset()
        assert not any(asked.startswith(('ancestor', 'changed')) for asked in git.asked)

    @pytest.mark.parametrize('seen', [create_seen('R1', base=None), create_seen('R1', base='gone')])
    async def test_unresolved_base_asks_no_comparison(
        self, tmp_path: Path, seen: TaskRecord
    ) -> None:
        git = FakeGit()

        verify = await gather(git, tmp_path, seen, create_request('R1'))

        assert not verify.git.base_resolves
        assert (verify.git.base_is_ancestor, verify.git.changed_files) == (False, frozenset())
        assert not any(asked.startswith(('ancestor', 'changed')) for asked in git.asked)

    async def test_base_not_an_ancestor_is_reported(self, tmp_path: Path) -> None:
        verify = await gather(
            FakeGit(ancestor=False), tmp_path, create_seen('R1'), create_request('R1')
        )

        assert not verify.git.base_is_ancestor


class TestPlanTaskBrief:
    async def test_missing_brief_has_no_text(self, tmp_path: Path) -> None:
        verify = await gather(FakeGit(), tmp_path, create_seen(), create_request())

        assert verify.brief == Brief(text=None)
        assert verify.git.named_commit is None

    async def test_brief_text_is_read_and_its_commit_resolved(self, tmp_path: Path) -> None:
        text = f'## ASKED\n\n## DONE\ncommit: {NAMED}\n'
        write_brief(tmp_path, 3, text)
        git = FakeGit(resolving={'work': COMMIT, 'main': BASE, NAMED: NAMED})

        verify = await gather(git, tmp_path, create_seen(), create_request())

        assert verify.brief == Brief(text=text)
        assert verify.git.named_commit == NAMED

    async def test_named_commit_that_does_not_resolve_is_dropped(self, tmp_path: Path) -> None:
        write_brief(tmp_path, 3, f'## DONE\ncommit: {NAMED}\n')

        verify = await gather(FakeGit(), tmp_path, create_seen(), create_request())

        assert verify.git.named_commit is None

    async def test_brief_without_a_done_commit_names_none(self, tmp_path: Path) -> None:
        write_brief(tmp_path, 3, '## ASKED\n')

        verify = await gather(FakeGit(), tmp_path, create_seen(), create_request())

        assert verify.brief == Brief(text='## ASKED\n')
        assert verify.git.named_commit is None

    async def test_residual_task_reads_no_brief(self, tmp_path: Path) -> None:
        write_brief(tmp_path, 3, f'## DONE\ncommit: {NAMED}\n')

        verify = await gather(FakeGit(), tmp_path, create_seen('R3'), create_request('R3'))

        assert verify.brief is None


class TestLoadBrief:
    @pytest.fixture
    def sources(self, tmp_path: Path) -> VerificationSources:
        return VerificationSources(git=FakeGit(), workspace=workspace_of(tmp_path))

    async def test_load_brief_of_a_residual_task_is_none(
        self, tmp_path: Path, sources: VerificationSources
    ) -> None:
        write_brief(tmp_path, 3, '## ASKED\n')

        assert await load_brief(sources, create_request('R3')) is None

    async def test_load_brief_of_a_plan_task_reads_the_file(
        self, tmp_path: Path, sources: VerificationSources
    ) -> None:
        write_brief(tmp_path, 3, '## ASKED\n')

        assert await load_brief(sources, create_request('T3')) == Brief(text='## ASKED\n')

    async def test_load_brief_without_a_file_has_no_text(
        self, sources: VerificationSources
    ) -> None:
        assert await load_brief(sources, create_request('T3')) == Brief(text=None)


class TestResolveNamedCommit:
    @pytest.mark.parametrize('brief', [None, Brief(text=None), Brief(text='## ASKED\n')])
    async def test_resolve_named_commit_without_a_named_commit_asks_git_nothing(
        self, brief: Brief | None
    ) -> None:
        git = FakeGit()

        assert await resolve_named_commit(git, brief) is None
        assert git.asked == []

    async def test_resolve_named_commit_returns_the_resolved_commit(self) -> None:
        git = FakeGit(resolving={NAMED: NAMED})

        assert await resolve_named_commit(git, Brief(text=f'## DONE\ncommit: {NAMED}\n')) == NAMED

    async def test_resolve_named_commit_drops_a_commit_git_cannot_resolve(self) -> None:
        brief = Brief(text=f'## DONE\ncommit: {NAMED}\n')

        assert await resolve_named_commit(FakeGit(), brief) is None
