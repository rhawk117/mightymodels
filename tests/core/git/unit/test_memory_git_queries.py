"""The git query contract against the in-memory backend."""

from typing import TYPE_CHECKING

from mightymodels_core.git import Git, ProcessGit

from tests.core.git.fakes import InMemoryGit
from tests.core.git.git_queries_suite import GitQueriesContract

if TYPE_CHECKING:
    from tests.core.git.git_builders import ScriptedHarness


class TestMemoryGitQueries(GitQueriesContract):
    pass


class TestProtocol:
    def test_the_process_implementation_is_a_git(self, scripted: ScriptedHarness) -> None:
        assert isinstance(scripted.git, Git)

    def test_the_fake_is_a_git(self) -> None:
        assert isinstance(InMemoryGit(), Git)

    def test_the_process_implementation_is_a_process_git(self, scripted: ScriptedHarness) -> None:
        assert isinstance(scripted.git, ProcessGit)
