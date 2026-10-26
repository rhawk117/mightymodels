from typing import TYPE_CHECKING

import pytest
from mightymodels_hooks.pre_compact import repository_facts

from tests.core.git.fakes import InMemoryGit

if TYPE_CHECKING:
    from mightymodels_core.snapshot.records import RepositoryFacts


@pytest.fixture
def git() -> InMemoryGit:
    git = InMemoryGit(branch='feat/port-it', dirty=['a.py'], untracked=['b.py'])
    git.history.commit('a.py')
    return git


@pytest.fixture
def unreadable_git() -> InMemoryGit:
    return InMemoryGit(branch=None, dirty=None)


class TestRepositoryFacts:
    async def test_facts_name_the_branch_head_and_dirty_paths(self, git: InMemoryGit) -> None:
        facts: RepositoryFacts = await repository_facts(git)
        assert facts.branch == 'feat/port-it'
        assert facts.head == git.history.head()
        assert facts.dirty == ('a.py', 'b.py')
        assert facts.refusal is None

    async def test_a_detached_head_and_unreadable_status_stay_unknown(
        self, unreadable_git: InMemoryGit
    ) -> None:
        facts = await repository_facts(unreadable_git)
        assert facts.branch is None
        assert facts.dirty is None
