from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.git import GitMissingError, UntrackedFiles
from mightymodels_core.primitives import Slug
from mightymodels_core.ticket_closing.records import BranchFacts
from mightymodels_core.tickets import TicketRecord
from mightymodels_mcp.ticket.close_facts import PreparedClose, gather_close_facts

from tests.core.ticket_closing.closing_builders import create_ticket_section

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet
    from mightymodels_core.git import Checkout, GitRefusal
    from mightymodels_core.ticket_closing.records import CloseFacts

BRANCH = 'feat/close'
HEAD = 'a' * 40


@dataclass(slots=True, kw_only=True)
class FakeGit:
    refused: GitRefusal | None = None
    branch_exists: bool = True
    unpushed: int | None = 0
    current: str | None = 'main'
    dirty: list[str] | None = field(default_factory=list)
    asked: list[str] = field(default_factory=list)

    async def refusal(self) -> GitRefusal | None:
        self.asked.append('refusal')
        return self.refused

    async def checkout(self) -> Checkout | GitRefusal:
        raise NotImplementedError

    async def common_directory(self) -> Path | None:
        raise NotImplementedError

    async def is_ancestor(self, base: str, commit: str) -> bool:
        raise NotImplementedError

    async def changed_files(self, base: str, commit: str) -> set[str]:
        raise NotImplementedError

    async def resolve_head(self) -> str | None:
        self.asked.append('head')
        return HEAD

    async def resolve_commit(self, revision: str) -> str | None:
        self.asked.append(f'commit {revision}')
        return HEAD if self.branch_exists else None

    async def current_branch(self) -> str | None:
        self.asked.append('current')
        return self.current

    async def dirty_paths(self, *, untracked: UntrackedFiles) -> list[str] | None:
        assert untracked is UntrackedFiles.NO
        self.asked.append('dirty')
        return self.dirty

    async def commits_on_no_remote(self, branch: str) -> int | None:
        self.asked.append(f'unpushed {branch}')
        return self.unpushed


def prepare(branch: str = BRANCH, *, debug_note: bool = False) -> PreparedClose:
    section = replace(create_ticket_section(), branch=branch)
    seen = TicketRecord(
        id=1, slug=Slug('probe'), status='staged', section=section, investigations=()
    )
    return PreparedClose(seen=seen, debug_note=debug_note)


async def gather(git: FakeGit, prepared: PreparedClose) -> CloseFacts:
    return await gather_close_facts(git, prepared)


def branch_cases() -> pytest.MarkDecorator:
    cases: list[ParameterSet] = [
        pytest.param(
            FakeGit(branch_exists=False),
            BranchFacts(exists=False, unpushed=None, checked_out=False, dirty=None),
            id='absent',
        ),
        pytest.param(
            FakeGit(unpushed=3),
            BranchFacts(exists=True, unpushed=3, checked_out=False, dirty=None),
            id='unpushed-not-checked-out',
        ),
        pytest.param(
            FakeGit(current=BRANCH, dirty=['a.py', 'b.py']),
            BranchFacts(exists=True, unpushed=0, checked_out=True, dirty=2),
            id='checked-out-dirty',
        ),
        pytest.param(
            FakeGit(current=BRANCH, dirty=None, unpushed=None),
            BranchFacts(exists=True, unpushed=None, checked_out=True, dirty=None),
            id='git-could-not-count',
        ),
    ]
    return pytest.mark.parametrize(('git', 'expected'), cases)


class TestGatherCloseFacts:
    @branch_cases()
    async def test_branch_facts_come_from_git(self, git: FakeGit, expected: BranchFacts) -> None:
        facts = await gather(git, prepare())

        assert facts.branch == expected
        assert (facts.head, facts.git_refusal) == (HEAD, None)

    async def test_dirty_paths_are_asked_only_for_the_checked_out_branch(self) -> None:
        git = FakeGit(current='main')

        await gather(git, prepare())

        assert 'dirty' not in git.asked

    async def test_refusal_asks_nothing_else(self) -> None:
        git = FakeGit(refused=GitMissingError())

        facts = await gather(git, prepare(debug_note=True))

        assert git.asked == ['refusal']
        assert (facts.git_refusal, facts.head, facts.branch) == (str(GitMissingError()), None, None)
        assert facts.debug_note

    async def test_unsafe_branch_name_is_never_given_to_git(self) -> None:
        git = FakeGit()

        facts = await gather(git, prepare('--upload-pack=x'))

        assert facts.branch is None
        assert git.asked == ['refusal', 'head']
