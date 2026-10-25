"""Real git outside a repository."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.git import GitCommand, NotARepositoryError, ProcessGit
from mightymodels_core.process import SubprocessRunner

if TYPE_CHECKING:
    from pathlib import Path


class TestOutsideARepository:
    @pytest.fixture
    def bare_directory_git(self, tmp_path: Path) -> ProcessGit:
        command = GitCommand(root=tmp_path, executable='git', processes=SubprocessRunner())
        return ProcessGit(command=command)

    async def test_a_directory_outside_a_repository_is_refused(
        self, bare_directory_git: ProcessGit
    ) -> None:
        assert isinstance(await bare_directory_git.refusal(), NotARepositoryError)
