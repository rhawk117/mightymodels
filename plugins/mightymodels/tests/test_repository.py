import os
from collections.abc import Callable
from pathlib import Path

import pytest
from mightymodels_plugin.db.repository import (
    DATABASE_NAME,
    EXCLUDE_LINE,
    STATE_DIRECTORY,
    NotARepositoryError,
    find_root,
    open_repository,
)

type GitRunner = Callable[..., str]


class TestFindRoot:
    def test_uses_claude_project_dir_when_set(self, tmp_path: Path) -> None:
        project = tmp_path.joinpath('project')

        assert find_root({'CLAUDE_PROJECT_DIR': str(project)}, tmp_path) == project

    @pytest.mark.parametrize(
        'environ',
        [pytest.param({}, id='unset'), pytest.param({'CLAUDE_PROJECT_DIR': ''}, id='empty')],
    )
    def test_falls_back_to_the_working_directory(
        self, environ: dict[str, str], tmp_path: Path
    ) -> None:
        assert find_root(environ, tmp_path) == tmp_path

    def test_lookup_from_the_process_environment(
        self, repository: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(repository))
        monkeypatch.chdir(tmp_path)

        assert find_root(os.environ, Path.cwd()) == repository

    def test_lookup_from_the_process_working_directory(
        self, repository: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
        monkeypatch.chdir(repository)

        assert find_root(os.environ, Path.cwd()) == repository.resolve()


class TestOpenRepository:
    def exclude_lines(self, repository: Path) -> list[str]:
        exclude = repository.joinpath('.git', 'info', 'exclude')
        return exclude.read_text(encoding='utf-8').splitlines()

    def test_creates_the_database(self, repository: Path) -> None:
        open_repository(repository).dispose()

        assert repository.joinpath(STATE_DIRECTORY, DATABASE_NAME).is_file()

    def test_excludes_the_state_directory_from_git(self, repository: Path) -> None:
        open_repository(repository).dispose()

        assert EXCLUDE_LINE in self.exclude_lines(repository)

    def test_excluded_state_does_not_show_in_git_status(
        self, repository: Path, git: GitRunner
    ) -> None:
        open_repository(repository).dispose()

        assert git(repository, 'status', '--porcelain') == ''

    def test_is_idempotent(self, repository: Path) -> None:
        open_repository(repository).dispose()
        open_repository(repository).dispose()

        assert self.exclude_lines(repository).count(EXCLUDE_LINE) == 1

    def test_keeps_existing_exclude_lines_without_a_trailing_newline(
        self, repository: Path
    ) -> None:
        exclude = repository.joinpath('.git', 'info', 'exclude')
        exclude.write_text('*.log', encoding='utf-8')

        open_repository(repository).dispose()

        assert self.exclude_lines(repository) == ['*.log', EXCLUDE_LINE]

    def test_linked_worktree_writes_to_the_common_git_dir(
        self, repository: Path, tmp_path: Path, git: GitRunner
    ) -> None:
        git(
            repository,
            '-c',
            'user.name=t',
            '-c',
            'user.email=t@t',
            'commit',
            '--allow-empty',
            '-m',
            'init',
        )
        worktree = tmp_path.joinpath('worktree')
        git(repository, 'worktree', 'add', '--quiet', str(worktree), '-b', 'other')

        open_repository(worktree).dispose()

        assert EXCLUDE_LINE in self.exclude_lines(repository)
        assert worktree.joinpath(STATE_DIRECTORY, DATABASE_NAME).is_file()

    def test_refuses_a_directory_outside_a_repository(self, tmp_path: Path) -> None:
        outside = tmp_path.joinpath('outside')
        outside.mkdir()

        with pytest.raises(NotARepositoryError) as error:
            open_repository(outside)

        assert error.value.root == outside
        assert not outside.joinpath(STATE_DIRECTORY).exists()
