from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from mightymodels_core.git import (
    GIT_TIMEOUT_SECONDS,
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

from .conftest import SCRIPTED_ROOT, create_scripted_harness

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import ParameterSet
    from mightymodels_core.git import Git

    from .conftest import ScriptedHarness

HOSTILE = {'option': '--output=/tmp/pwned', 'newline': 'main\n', 'dash': '-b'}
NOT_A_REPOSITORY = CompletedRun(exit=128, stdout='', stderr='fatal: not a git repository\n')
FAILURE_DETAIL = 'git refused to start'


@dataclass(slots=True, kw_only=True, frozen=True)
class Operation:
    name: str
    method: str
    arguments: tuple[Any, ...] = ()
    keywords: dict[str, Any] | None = None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)

    async def ask(self, git: Git) -> object:
        return await getattr(git, self.method)(*self.arguments, **(self.keywords or {}))


def every_operation_cases() -> pytest.MarkDecorator:
    operations = [
        Operation(name='refusal', method='refusal'),
        Operation(name='checkout', method='checkout'),
        Operation(name='common-directory', method='common_directory'),
        Operation(name='resolve-head', method='resolve_head'),
        Operation(name='resolve-commit', method='resolve_commit', arguments=('main',)),
        Operation(name='is-ancestor', method='is_ancestor', arguments=('main', 'HEAD')),
        Operation(name='changed-files', method='changed_files', arguments=('main', 'HEAD')),
        Operation(name='current-branch', method='current_branch'),
        Operation(
            name='dirty-paths',
            method='dirty_paths',
            keywords={'untracked': UntrackedFiles.NORMAL},
        ),
        Operation(name='commits-on-no-remote', method='commits_on_no_remote', arguments=('main',)),
    ]
    return pytest.mark.parametrize('operation', [operation.param for operation in operations])


def hostile_operation_cases() -> pytest.MarkDecorator:
    operations = [
        Operation(
            name=f'{method}-{index}-{name}',
            method=method,
            arguments=tuple(hostile if position == index else 'main' for position in range(count)),
        )
        for method, count in (('resolve_commit', 1), ('is_ancestor', 2), ('changed_files', 2))
        for index in range(count)
        for name, hostile in HOSTILE.items()
    ]
    operations.extend(
        Operation(
            name=f'commits_on_no_remote-{name}',
            method='commits_on_no_remote',
            arguments=(hostile,),
        )
        for name, hostile in HOSTILE.items()
    )
    return pytest.mark.parametrize('operation', [operation.param for operation in operations])


class TestRefusedBeforeAnyProcessStarts:
    @hostile_operation_cases()
    async def test_a_hostile_revision_is_refused_and_no_process_starts(
        self, scripted: ScriptedHarness, operation: Operation
    ) -> None:
        with pytest.raises(UnsafeRevisionError):
            await operation.ask(scripted.git)

        assert scripted.runner.runs == []

    async def test_the_refusal_names_the_hostile_revision(self, scripted: ScriptedHarness) -> None:
        with pytest.raises(UnsafeRevisionError) as refusal:
            await scripted.git.is_ancestor('main', '--all')

        assert refusal.value.revision == '--all'

    async def test_a_plain_revision_starts_a_process(self, scripted: ScriptedHarness) -> None:
        await scripted.git.resolve_commit('main')

        assert len(scripted.runner.runs) == 1


class TestTimeout:
    @every_operation_cases()
    async def test_every_operation_runs_under_thirty_seconds(
        self, scripted: ScriptedHarness, operation: Operation
    ) -> None:
        await operation.ask(scripted.git)

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
