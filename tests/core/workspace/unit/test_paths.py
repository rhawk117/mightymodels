"""Finding the project root from the environment and the working directory."""

from pathlib import Path

from mightymodels_core.workspace import PROJECT_DIR_VARIABLE, find_root


class TestFindRoot:
    def test_the_project_directory_variable_wins_over_the_working_directory(self) -> None:
        root = find_root({PROJECT_DIR_VARIABLE: '/project'}, Path('/elsewhere'))

        assert root == Path('/project')

    def test_the_working_directory_is_the_root_without_the_variable(self) -> None:
        assert find_root({}, Path('/elsewhere')) == Path('/elsewhere')
