"""Repository harnesses for `ProcessGit` and `InMemoryGit`, and the revision strategies."""

import operator
import string
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest
from hypothesis import strategies as st
from mightymodels_core.git import Checkout, GitCommand, ProcessGit
from mightymodels_core.process import CompletedRun, SubprocessRunner

from tests.core.git.fakes import (
    ANSWERED,
    CommitHistory,
    InMemoryGit,
    ScriptedRunner,
)

if TYPE_CHECKING:
    from mightymodels_core.process import RunOutcome

SCRIPTED_ROOT = Path('/repository')
GIT_ROOT_NAME = 'repository'
ORIGIN_URL = 'https://github.com/Owner/Repo.git'
TRACKED = 'a.txt'
ADDED = 'b.txt'
UNTRACKED = 'dirty.txt'
BRANCH = 'main'
COMMITS_ON_BRANCH = 2
PLAIN_FIRST = string.ascii_letters + string.digits
PLAIN_REST = PLAIN_FIRST + '._/-'


@dataclass(slots=True, kw_only=True, frozen=True)
class RepositoryHarness:
    git: ProcessGit | InMemoryGit
    root: Path
    first: str
    second: str


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptedHarness:
    git: ProcessGit
    runner: ScriptedRunner


async def run_git(root: Path, *arguments: str) -> str:
    identity = ['-c', 'user.name=Tester', '-c', 'user.email=tester@example.com']
    done = await SubprocessRunner().run(['git', *identity, *arguments], timeout=30, cwd=root)
    assert isinstance(done, CompletedRun)
    assert done.exit == 0, done.stderr
    return done.stdout.strip()


async def commit_file(root: Path, name: str) -> str:
    await anyio.Path(root, name).write_text(name)
    await run_git(root, 'add', name)
    await run_git(root, 'commit', '--message', name)
    return await run_git(root, 'rev-parse', 'HEAD')


async def create_process_harness(root: Path) -> RepositoryHarness:
    await anyio.Path(root).mkdir()
    await run_git(root, 'init', '--initial-branch', BRANCH)
    await run_git(root, 'remote', 'add', 'origin', ORIGIN_URL)
    first = await commit_file(root, TRACKED)
    second = await commit_file(root, ADDED)
    await anyio.Path(root, TRACKED).write_text('changed')
    await anyio.Path(root, UNTRACKED).write_text(UNTRACKED)
    command = GitCommand(root=root, executable='git', processes=SubprocessRunner())
    return RepositoryHarness(git=ProcessGit(command=command), root=root, first=first, second=second)


def create_memory_harness(root: Path) -> RepositoryHarness:
    history = CommitHistory(branches=(BRANCH,))
    memory = InMemoryGit(
        history=history,
        branch=BRANCH,
        checkout_at=Checkout(toplevel=root, origin_url=ORIGIN_URL),
        common=root.joinpath('.git'),
        dirty=(TRACKED,),
        untracked=(UNTRACKED,),
        unpushed={BRANCH: COMMITS_ON_BRANCH},
    )
    first = history.commit(TRACKED)
    second = history.commit(ADDED)
    return RepositoryHarness(git=memory, root=root, first=first, second=second)


def git_backend_cases() -> pytest.MarkDecorator:
    process = pytest.param('process', id='process', marks=pytest.mark.integration)
    memory = pytest.param('memory', id='memory')
    return pytest.mark.parametrize('harness', [process, memory], indirect=True)


def create_scripted_harness(
    reply: RunOutcome = ANSWERED, executable: str | None = 'git'
) -> ScriptedHarness:
    runner = ScriptedRunner(reply=reply)
    command = GitCommand(root=SCRIPTED_ROOT, executable=executable, processes=runner)
    return ScriptedHarness(git=ProcessGit(command=command), runner=runner)


def insert_character(name: str, character: str, position: int) -> str:
    return name[:position] + character + name[position:]


@st.composite
def names_with_a_foreign_character(draw: st.DrawFn) -> str:
    name = draw(PLAIN_NAMES)
    position = draw(st.integers(min_value=0, max_value=len(name)))
    character = draw(st.characters(exclude_characters=PLAIN_REST))
    return insert_character(name, character, position)


PLAIN_NAMES = st.builds(
    operator.add,
    st.text(alphabet=PLAIN_FIRST, min_size=1, max_size=1),
    st.text(alphabet=PLAIN_REST),
)
REFUSED_REVISIONS = st.one_of(
    st.just(''),
    st.builds(operator.add, st.sampled_from('-./'), PLAIN_NAMES),
    names_with_a_foreign_character(),
)
