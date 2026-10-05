"""Workspace containment, discovery and source-root detection."""

from functools import partial
from pathlib import Path
from types import MappingProxyType

import pytest
from python_harness.core.errors import (
    PathOutsideWorkspaceError,
    TargetPathMissingError,
    WorkspaceRootMissingError,
)
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import (
    DiscoveryOptions,
    Workspace,
    find_ancestor,
    find_search_boundary,
    has_entry,
    list_ancestors_to,
    open_workspace,
)


class TestResolve:
    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({'src/pkg/__init__.py': ''})

    @pytest.mark.parametrize(
        'escaping',
        [pytest.param('../outside.py', id='parent'), pytest.param('/etc', id='absolute')],
    )
    def test_rejects_paths_escaping_the_root(self, workspace: Workspace, escaping: str) -> None:
        with pytest.raises(PathOutsideWorkspaceError):
            workspace.resolve(escaping)

    def test_relative_paths_are_posix_and_root_relative(self, workspace: Workspace) -> None:
        resolved = workspace.resolve('src/pkg/__init__.py')

        assert workspace.relative(resolved) == 'src/pkg/__init__.py'


class TestDiscovery:
    FILES = MappingProxyType(
        {
            'src/pkg/__init__.py': '',
            'src/pkg/core.py': 'VALUE = 1\n',
            'src/pkg/notes.txt': 'not python\n',
            '.venv/lib/site.py': 'ignored = True\n',
            'src/pkg/__pycache__/core.py': 'ignored = True\n',
        }
    )

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    def test_finds_python_files_and_skips_excluded_directories(self, workspace: Workspace) -> None:
        found = tuple(workspace.relative(path) for path in workspace.python_files('.'))

        assert found == ('src/pkg/__init__.py', 'src/pkg/core.py')

    @pytest.mark.parametrize(
        ('target', 'expected'),
        [
            pytest.param('src/pkg/core.py', ('src/pkg/core.py',), id='python-file'),
            pytest.param('src/pkg/notes.txt', (), id='non-python-file'),
        ],
    )
    def test_single_file_targets(
        self, workspace: Workspace, target: str, expected: tuple[str, ...]
    ) -> None:
        found = tuple(workspace.relative(path) for path in workspace.python_files(target))

        assert found == expected

    def test_src_directory_is_a_source_root(self, workspace: Workspace) -> None:
        assert workspace.source_roots == (workspace.root.joinpath('src'),)

    @pytest.mark.parametrize(
        'target',
        [
            pytest.param('src/pkg/missing.py', id='missing-file'),
            pytest.param('src/pkgg', id='mistyped-directory'),
        ],
    )
    def test_missing_target_is_reported(self, workspace: Workspace, target: str) -> None:
        with pytest.raises(TargetPathMissingError):
            workspace.python_files(target)


class TestPythonFilesIn:
    FILES = MappingProxyType(
        {
            'src/pkg/__init__.py': '',
            'src/pkg/core.py': 'VALUE = 1\n',
            'src/app.py': 'RUN = 1\n',
        }
    )

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    @pytest.mark.parametrize(
        ('paths', 'expected'),
        [
            pytest.param(
                ('src/pkg', 'src/pkg/core.py'),
                ('src/pkg/__init__.py', 'src/pkg/core.py'),
                id='overlapping-paths-report-a-module-once',
            ),
            pytest.param(
                ('src/pkg/core.py', 'src/app.py'),
                ('src/app.py', 'src/pkg/core.py'),
                id='union-is-sorted-across-paths',
            ),
        ],
    )
    def test_python_files_of_every_path_are_one_sorted_union(
        self, workspace: Workspace, paths: tuple[str, ...], expected: tuple[str, ...]
    ) -> None:
        found = workspace.python_files_in(paths)

        assert tuple(workspace.relative(path) for path in found) == expected

    def test_a_missing_path_is_reported(self, workspace: Workspace) -> None:
        with pytest.raises(TargetPathMissingError):
            workspace.python_files_in(('src/pkg', 'src/pkgg'))


class TestEscapingSymlinks:
    @pytest.fixture
    def outside(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        directory = tmp_path_factory.mktemp('outside')
        directory.joinpath('secret.py').write_text('TOKEN = 1\n', encoding='utf-8')
        return directory

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder, outside: Path) -> Workspace:
        workspace = project_builder.write({'pkg/core.py': 'VALUE = 1\n'})
        package = workspace.root.joinpath('pkg')
        package.joinpath('linked.py').symlink_to(outside.joinpath('secret.py'))
        package.joinpath('linked_package').symlink_to(outside, target_is_directory=True)
        return workspace

    def test_files_and_directories_resolving_outside_the_root_are_skipped(
        self, workspace: Workspace
    ) -> None:
        found = tuple(workspace.relative(path) for path in workspace.python_files('.'))

        assert found == ('pkg/core.py',)


class TestOpenWorkspace:
    def test_missing_root_is_reported(self, project_builder: ProjectBuilder) -> None:
        with pytest.raises(WorkspaceRootMissingError):
            open_workspace(project_builder.root.joinpath('absent'))

    def test_flat_layout_has_no_source_roots(self, project_builder: ProjectBuilder) -> None:
        workspace = project_builder.write({'pkg/__init__.py': ''})

        assert workspace.source_roots == ()


class TestIsTestPath:
    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write({})

    @pytest.mark.parametrize(
        ('path', 'expected'),
        [
            pytest.param('tests/test_orders.py', True, id='test-file-in-tests'),
            pytest.param('tests/support/builders.py', True, id='helper-under-tests'),
            pytest.param('test/helpers.py', True, id='helper-under-test'),
            pytest.param('src/shop/test_helpers.py', True, id='test-prefix-anywhere'),
            pytest.param('src/shop/orders_test.py', True, id='test-suffix-anywhere'),
            pytest.param('src/shop/tests/fixtures.py', True, id='nested-tests-package'),
            pytest.param('src/shop/orders.py', False, id='source-module'),
            pytest.param('src/shop/contest.py', False, id='test-inside-a-word'),
            pytest.param('src/shop/latest.py', False, id='test-suffix-inside-a-word'),
            pytest.param('src/tests.py', False, id='module-named-tests'),
            pytest.param('src/test.py', False, id='module-named-test'),
        ],
    )
    def test_test_directory_or_test_file_name_marks_a_test(
        self, workspace: Workspace, path: str, *, expected: bool
    ) -> None:
        assert workspace.is_test_path(path) is expected


class TestCustomTestDirectories:
    OPTIONS = DiscoveryOptions(test_directory_names=frozenset({'specs'}))

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return open_workspace(project_builder.root, self.OPTIONS)

    @pytest.mark.parametrize(
        ('path', 'expected'),
        [
            pytest.param('specs/builders.py', True, id='configured-directory'),
            pytest.param('tests/builders.py', False, id='default-directory-replaced'),
            pytest.param('specs_old/builders.py', False, id='directory-name-prefix'),
        ],
    )
    def test_configured_directory_names_decide(
        self, workspace: Workspace, path: str, *, expected: bool
    ) -> None:
        assert workspace.is_test_path(path) is expected


class TestAncestors:
    def test_the_nearest_ancestor_holding_an_entry_is_found(
        self, project_builder: ProjectBuilder
    ) -> None:
        project_builder.write({'pyproject.toml': '', 'src/pkg/mod.py': ''})
        start = project_builder.root.joinpath('src', 'pkg')

        found = find_ancestor(start, partial(has_entry, name='pyproject.toml'))

        assert found == project_builder.root

    def test_ancestors_stop_at_the_boundary(self, project_builder: ProjectBuilder) -> None:
        start = project_builder.root.joinpath('a', 'b')

        found = list_ancestors_to(start, project_builder.root)

        assert found == (start, start.parent, project_builder.root)

    def test_a_boundary_that_is_not_an_ancestor_keeps_only_the_start(
        self, project_builder: ProjectBuilder
    ) -> None:
        start = project_builder.root.joinpath('a')

        assert list_ancestors_to(start, project_builder.root.joinpath('b')) == (start,)

    def test_the_first_marker_found_sets_the_boundary(
        self, project_builder: ProjectBuilder
    ) -> None:
        project_builder.write({'.git/HEAD': '', 'pkg/pyproject.toml': ''})
        start = project_builder.root.joinpath('pkg')

        boundary = find_search_boundary(start, ('.git', 'pyproject.toml'))

        assert boundary == project_builder.root

    def test_without_a_marker_the_start_is_the_boundary(
        self, project_builder: ProjectBuilder
    ) -> None:
        start = project_builder.root.joinpath('lonely')

        assert find_search_boundary(start, ('no-such-marker',)) == start
