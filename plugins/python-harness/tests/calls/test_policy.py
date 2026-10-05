"""Whether requested target paths are modules the project discovered."""

from types import MappingProxyType

import pytest
from python_harness.calls.errors import UnknownTargetPathsError
from python_harness.calls.policy import check_targets_known
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.imports.domain import ProjectIndex
from python_harness.imports.services import load_project_index


class TestCheckTargetsKnown:
    FILES = MappingProxyType(
        {
            'src/shop/__init__.py': '',
            'src/shop/broken.py': 'def broken(:\n',
            'build/generated.py': 'VALUE = 1\n',
        }
    )
    KNOWN = frozenset({'src/shop/__init__.py', 'src/shop/broken.py'})
    UNDISCOVERED = frozenset({'build/generated.py'})

    @pytest.fixture
    def index(self, project_builder: ProjectBuilder) -> ProjectIndex:
        return load_project_index(project_builder.write(self.FILES))

    def test_parsed_and_unparsable_modules_are_known(self, index: ProjectIndex) -> None:
        assert check_targets_known(index, self.KNOWN) is None

    def test_undiscovered_paths_are_returned_as_the_problem(self, index: ProjectIndex) -> None:
        problem = check_targets_known(index, self.KNOWN | self.UNDISCOVERED)

        assert isinstance(problem, UnknownTargetPathsError)
        assert problem.paths == self.UNDISCOVERED
