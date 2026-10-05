"""Changed-file listing between a base and a head revision."""

import pytest
from python_harness.core.errors import GitCommandError
from python_harness.core.git import list_changed_python_files
from python_harness.core.tests.fixtures import GitProject
from python_harness.core.workspace import Workspace, open_workspace


class TestListChangedPythonFiles:
    @pytest.fixture
    def workspace(self, git_project: GitProject) -> Workspace:
        git_project.commit({'pkg/kept.py': 'a = 1\n', 'pkg/removed.py': 'b = 1\n'}, 'base')
        git_project.switch_to_new_branch('feature')
        git_project.git('rm', '--quiet', 'pkg/removed.py')
        return git_project.commit(
            {'pkg/added.py': 'c = 1\n', 'pkg/kept.py': 'a = 2\n', 'README.md': 'x\n'},
            'change',
        )

    def test_lists_added_and_modified_python_files_only(self, workspace: Workspace) -> None:
        changed = list_changed_python_files(workspace, 'main', 'HEAD')

        assert changed == ('pkg/added.py', 'pkg/kept.py')

    def test_unknown_base_is_reported(self, workspace: Workspace) -> None:
        with pytest.raises(GitCommandError):
            list_changed_python_files(workspace, 'no-such-branch', 'HEAD')

    def test_reported_failure_keeps_git_stderr(self, workspace: Workspace) -> None:
        with pytest.raises(GitCommandError) as caught:
            list_changed_python_files(workspace, 'no-such-branch', 'HEAD')

        assert 'no-such-branch' in caught.value.stderr


class TestWorkspaceInsideTheRepository:
    @pytest.fixture
    def workspace(self, git_project: GitProject) -> Workspace:
        git_project.commit({'service/pkg/core.py': 'a = 1\n', 'other/x.py': 'b = 1\n'}, 'base')
        git_project.switch_to_new_branch('feature')
        git_project.commit({'service/pkg/core.py': 'a = 2\n', 'other/x.py': 'b = 2\n'}, 'change')
        return open_workspace(git_project.builder.root.joinpath('service'))

    def test_paths_are_relative_to_the_workspace_and_scoped_to_it(
        self, workspace: Workspace
    ) -> None:
        assert list_changed_python_files(workspace, 'main', 'HEAD') == ('pkg/core.py',)
