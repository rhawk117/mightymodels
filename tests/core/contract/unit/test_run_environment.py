"""The environment a contract command inherits."""

from mightymodels_core.contract import child_environment

PARENT = {
    'PATH': '/usr/bin',
    'HOME': '/home/someone',
    'UV_PROJECT': '/project',
    'UV_PROJECT_ENVIRONMENT': '/project/.venv',
    'VIRTUAL_ENV': '/project/.venv',
}


class TestChildEnvironment:
    def test_children_inherit_the_environment_minus_the_uv_project_names(self) -> None:
        assert child_environment(PARENT) == {'PATH': '/usr/bin', 'HOME': '/home/someone'}

    def test_the_parent_environment_is_left_as_it_was(self) -> None:
        parent = dict(PARENT)

        child_environment(parent)

        assert parent == PARENT

    def test_an_environment_without_the_names_is_copied_whole(self) -> None:
        assert child_environment({'PATH': '/usr/bin'}) == {'PATH': '/usr/bin'}
