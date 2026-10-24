from typing import TYPE_CHECKING

import pytest
from mightymodels_core.git import Checkout, Git, GitUnavailableError, ProcessGit, UntrackedFiles
from mightymodels_core.primitives import RepositoryKey

from tests.core.git.fakes import InMemoryGit
from tests.core.git.git_builders import (
    ADDED,
    BRANCH,
    COMMITS_ON_BRANCH,
    ORIGIN_URL,
    TRACKED,
    UNTRACKED,
    git_backend_cases,
)

if TYPE_CHECKING:
    from tests.core.git.git_builders import RepositoryHarness, ScriptedHarness


class TestProtocol:
    def test_the_process_implementation_is_a_git(self, scripted: ScriptedHarness) -> None:
        assert isinstance(scripted.git, Git)

    def test_the_fake_is_a_git(self) -> None:
        assert isinstance(InMemoryGit(), Git)

    def test_the_process_implementation_is_a_process_git(self, scripted: ScriptedHarness) -> None:
        assert isinstance(scripted.git, ProcessGit)


@git_backend_cases()
class TestCheckoutState:
    async def test_the_repository_is_not_refused(self, harness: RepositoryHarness) -> None:
        assert await harness.git.refusal() is None

    async def test_checkout_names_the_toplevel_and_origin(self, harness: RepositoryHarness) -> None:
        checkout = await harness.git.checkout()

        assert checkout == Checkout(toplevel=harness.root, origin_url=ORIGIN_URL)
        assert isinstance(checkout, Checkout)
        assert checkout.repository_key() == RepositoryKey('owner/repo')

    async def test_the_current_branch_is_named(self, harness: RepositoryHarness) -> None:
        assert await harness.git.current_branch() == BRANCH

    async def test_the_common_directory_is_the_git_directory(
        self, harness: RepositoryHarness
    ) -> None:
        assert await harness.git.common_directory() == harness.root.joinpath('.git')


@git_backend_cases()
class TestResolution:
    async def test_head_is_the_newest_commit(self, harness: RepositoryHarness) -> None:
        assert await harness.git.resolve_head() == harness.second

    async def test_a_commit_resolves_from_its_sha(self, harness: RepositoryHarness) -> None:
        assert await harness.git.resolve_commit(harness.first) == harness.first

    async def test_a_branch_resolves_to_its_commit(self, harness: RepositoryHarness) -> None:
        assert await harness.git.resolve_commit(BRANCH) == harness.second

    async def test_an_unknown_revision_does_not_resolve(self, harness: RepositoryHarness) -> None:
        assert await harness.git.resolve_commit('nothing-here') is None


@git_backend_cases()
class TestAncestry:
    async def test_an_older_commit_is_an_ancestor(self, harness: RepositoryHarness) -> None:
        assert await harness.git.is_ancestor(harness.first, harness.second) is True

    async def test_a_newer_commit_is_not_an_ancestor(self, harness: RepositoryHarness) -> None:
        assert await harness.git.is_ancestor(harness.second, harness.first) is False

    async def test_a_commit_is_its_own_ancestor(self, harness: RepositoryHarness) -> None:
        assert await harness.git.is_ancestor(harness.first, harness.first) is True

    async def test_an_unknown_ancestor_cannot_be_answered(self, harness: RepositoryHarness) -> None:
        with pytest.raises(GitUnavailableError):
            await harness.git.is_ancestor('nothing-here', harness.second)


@git_backend_cases()
class TestChangedFiles:
    async def test_changed_files_lists_what_the_range_added(
        self, harness: RepositoryHarness
    ) -> None:
        assert await harness.git.changed_files(harness.first, harness.second) == {ADDED}

    async def test_changed_files_of_an_empty_range_is_empty(
        self, harness: RepositoryHarness
    ) -> None:
        assert await harness.git.changed_files(harness.second, harness.second) == set()

    async def test_changed_files_of_an_unknown_range_cannot_be_listed(
        self, harness: RepositoryHarness
    ) -> None:
        with pytest.raises(GitUnavailableError):
            await harness.git.changed_files('nothing-here', harness.second)


@git_backend_cases()
class TestWorkingTree:
    async def test_dirty_paths_include_untracked_files_when_asked(
        self, harness: RepositoryHarness
    ) -> None:
        dirty = await harness.git.dirty_paths(untracked=UntrackedFiles.NORMAL)

        assert dirty == [TRACKED, UNTRACKED]

    async def test_dirty_paths_leave_untracked_files_out_when_told(
        self, harness: RepositoryHarness
    ) -> None:
        dirty = await harness.git.dirty_paths(untracked=UntrackedFiles.NO)

        assert dirty == [TRACKED]

    async def test_commits_on_no_remote_counts_the_branch(self, harness: RepositoryHarness) -> None:
        assert await harness.git.commits_on_no_remote(BRANCH) == COMMITS_ON_BRANCH

    async def test_commits_on_no_remote_of_an_unknown_branch_is_none(
        self, harness: RepositoryHarness
    ) -> None:
        assert await harness.git.commits_on_no_remote('nothing-here') is None
