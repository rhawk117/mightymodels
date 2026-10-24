from types import MappingProxyType
from typing import TYPE_CHECKING, get_protocol_members

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.git import (
    GIT_TIMEOUT_SECONDS,
    Git,
    GitCommand,
    GitMissingError,
    GitNoAnswerError,
    GitUnavailableError,
    NotARepositoryError,
    ProcessGit,
    UnsafeRevisionError,
    UntrackedFiles,
)
from mightymodels_core.process import CompletedRun, FailedRun, SubprocessRunner

from tests.core.git.git_builders import REFUSED_REVISIONS, SCRIPTED_ROOT, create_scripted_harness

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from pathlib import Path

    from tests.core.git.git_builders import ScriptedHarness

HOSTILE = {'option': '--output=/tmp/pwned', 'newline': 'main\n', 'dash': '-b'}
NOT_A_REPOSITORY = CompletedRun(exit=128, stdout='', stderr='fatal: not a git repository\n')
FAILURE_DETAIL = 'git refused to start'


type Revisions = tuple[str, ...]
type Operation = Callable[[Git, Revisions], Awaitable[object]]


async def ask_refusal(git: Git, _revisions: Revisions) -> object:
    return await git.refusal()


async def ask_checkout(git: Git, _revisions: Revisions) -> object:
    return await git.checkout()


async def ask_common_directory(git: Git, _revisions: Revisions) -> object:
    return await git.common_directory()


async def ask_resolve_head(git: Git, _revisions: Revisions) -> object:
    return await git.resolve_head()


async def ask_resolve_commit(git: Git, revisions: Revisions) -> object:
    return await git.resolve_commit(revisions[0])


async def ask_is_ancestor(git: Git, revisions: Revisions) -> object:
    return await git.is_ancestor(revisions[0], revisions[1])


async def ask_changed_files(git: Git, revisions: Revisions) -> object:
    return await git.changed_files(revisions[0], revisions[1])


async def ask_current_branch(git: Git, _revisions: Revisions) -> object:
    return await git.current_branch()


async def ask_dirty_paths(git: Git, _revisions: Revisions) -> object:
    return await git.dirty_paths(untracked=UntrackedFiles.NORMAL)


async def ask_commits_on_no_remote(git: Git, revisions: Revisions) -> object:
    return await git.commits_on_no_remote(revisions[0])


OPERATIONS: Mapping[str, Operation] = MappingProxyType({
    'refusal': ask_refusal,
    'checkout': ask_checkout,
    'common_directory': ask_common_directory,
    'resolve_head': ask_resolve_head,
    'resolve_commit': ask_resolve_commit,
    'is_ancestor': ask_is_ancestor,
    'changed_files': ask_changed_files,
    'current_branch': ask_current_branch,
    'dirty_paths': ask_dirty_paths,
    'commits_on_no_remote': ask_commits_on_no_remote,
})
REVISION_POSITIONS = (
    ('resolve_commit', 0),
    ('is_ancestor', 0),
    ('is_ancestor', 1),
    ('changed_files', 0),
    ('changed_files', 1),
    ('commits_on_no_remote', 0),
)
PLAIN_REVISIONS = ('main', 'HEAD')


class TestOperations:
    def test_the_operations_are_the_git_protocol_members(self) -> None:
        assert set(OPERATIONS) == set(get_protocol_members(Git))


class TestRefusedBeforeAnyProcessStarts:
    revision_positions = st.sampled_from(REVISION_POSITIONS)
    refused_revisions = REFUSED_REVISIONS

    @given(placement=revision_positions, revision=refused_revisions)
    @example(placement=('resolve_commit', 0), revision=HOSTILE['option'])
    @example(placement=('is_ancestor', 0), revision=HOSTILE['newline'])
    @example(placement=('is_ancestor', 1), revision=HOSTILE['dash'])
    @example(placement=('changed_files', 0), revision=HOSTILE['dash'])
    @example(placement=('changed_files', 1), revision=HOSTILE['option'])
    @example(placement=('commits_on_no_remote', 0), revision=HOSTILE['newline'])
    async def test_a_hostile_revision_is_refused_and_no_process_starts(
        self, placement: tuple[str, int], revision: str
    ) -> None:
        name, position = placement
        revisions = tuple(revision if index == position else 'main' for index in range(2))
        scripted = create_scripted_harness()

        with pytest.raises(UnsafeRevisionError):
            await OPERATIONS[name](scripted.git, revisions)

        assert scripted.runner.runs == []

    async def test_the_refusal_names_the_hostile_revision(self, scripted: ScriptedHarness) -> None:
        with pytest.raises(UnsafeRevisionError) as refusal:
            await scripted.git.is_ancestor('main', '--all')

        assert refusal.value.revision == '--all'

    async def test_a_plain_revision_starts_a_process(self, scripted: ScriptedHarness) -> None:
        await scripted.git.resolve_commit('main')

        assert len(scripted.runner.runs) == 1


class TestTimeout:
    operation_names = st.sampled_from(sorted(OPERATIONS))

    @given(name=operation_names)
    @example(name='refusal')
    @example(name='checkout')
    @example(name='common_directory')
    @example(name='resolve_head')
    @example(name='resolve_commit')
    @example(name='is_ancestor')
    @example(name='changed_files')
    @example(name='current_branch')
    @example(name='dirty_paths')
    @example(name='commits_on_no_remote')
    async def test_every_operation_runs_under_thirty_seconds(self, name: str) -> None:
        scripted = create_scripted_harness()

        await OPERATIONS[name](scripted.git, PLAIN_REVISIONS)

        timeouts = {run.timeout for run in scripted.runner.runs}
        assert scripted.runner.runs
        assert timeouts == {30}

    def test_the_default_timeout_is_thirty_seconds(self) -> None:
        assert GIT_TIMEOUT_SECONDS == 30


class TestCommandLine:
    async def test_the_command_runs_git_at_the_root(self, scripted: ScriptedHarness) -> None:
        await scripted.git.resolve_head()

        argv = scripted.runner.runs[0].argv
        assert argv == ('git', '-C', str(SCRIPTED_ROOT), 'rev-parse', '--verify', '--quiet', 'HEAD')

    async def test_changed_files_ends_the_options(self, scripted: ScriptedHarness) -> None:
        await scripted.git.changed_files('main', 'HEAD')

        assert scripted.runner.runs[0].argv[-2:] == ('main..HEAD', '--')

    async def test_untracked_files_are_asked_for_by_name(self, scripted: ScriptedHarness) -> None:
        await scripted.git.dirty_paths(untracked=UntrackedFiles.NO)

        assert scripted.runner.runs[0].argv[-1] == '--untracked-files=no'


class TestUnanswered:
    @pytest.fixture
    def without_executable(self) -> ScriptedHarness:
        return create_scripted_harness(executable=None)

    @pytest.fixture
    def not_found(self) -> ScriptedHarness:
        reply = FailedRun(kind='not_found', detail=FAILURE_DETAIL, stdout='', stderr='')
        return create_scripted_harness(reply)

    @pytest.fixture
    def timed_out(self) -> ScriptedHarness:
        reply = FailedRun(kind='timed_out', detail=FAILURE_DETAIL, stdout='', stderr='')
        return create_scripted_harness(reply)

    async def test_no_executable_starts_no_process(
        self, without_executable: ScriptedHarness
    ) -> None:
        refusal = await without_executable.git.refusal()

        assert isinstance(refusal, GitMissingError)
        assert without_executable.runner.runs == []

    async def test_a_missing_executable_is_reported_as_missing(
        self, not_found: ScriptedHarness
    ) -> None:
        assert isinstance(await not_found.git.refusal(), GitMissingError)

    async def test_a_timed_out_run_is_reported_with_its_detail(
        self, timed_out: ScriptedHarness
    ) -> None:
        refusal = await timed_out.git.checkout()

        assert isinstance(refusal, GitNoAnswerError)
        assert refusal.detail == FAILURE_DETAIL


class TestNotARepository:
    @pytest.fixture
    def not_a_repository(self) -> ScriptedHarness:
        return create_scripted_harness(NOT_A_REPOSITORY)

    async def test_a_failing_rev_parse_means_not_a_repository(
        self, not_a_repository: ScriptedHarness
    ) -> None:
        refusal = await not_a_repository.git.refusal()

        assert isinstance(refusal, NotARepositoryError)
        assert refusal.root == SCRIPTED_ROOT
        assert refusal.detail == 'fatal: not a git repository'

    async def test_checkout_outside_a_repository_is_refused(
        self, not_a_repository: ScriptedHarness
    ) -> None:
        assert isinstance(await not_a_repository.git.checkout(), NotARepositoryError)

    async def test_is_ancestor_raises_when_git_cannot_tell(
        self, not_a_repository: ScriptedHarness
    ) -> None:
        with pytest.raises(GitUnavailableError):
            await not_a_repository.git.is_ancestor('main', 'HEAD')

    async def test_changed_files_raises_when_git_cannot_list(
        self, not_a_repository: ScriptedHarness
    ) -> None:
        with pytest.raises(GitUnavailableError):
            await not_a_repository.git.changed_files('main', 'HEAD')


@pytest.mark.integration
class TestOutsideARepository:
    @pytest.fixture
    def bare_directory_git(self, tmp_path: Path) -> ProcessGit:
        command = GitCommand(root=tmp_path, executable='git', processes=SubprocessRunner())
        return ProcessGit(command=command)

    async def test_a_directory_outside_a_repository_is_refused(
        self, bare_directory_git: ProcessGit
    ) -> None:
        assert isinstance(await bare_directory_git.refusal(), NotARepositoryError)
