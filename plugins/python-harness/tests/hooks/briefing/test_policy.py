"""Which manifest group declares a package."""

import pytest
from python_harness.hooks.briefing.domain import Declaration
from python_harness.hooks.briefing.policy import classify_declaration
from python_harness.survey.domain import NO_MANIFEST, ProjectManifest


class TestClassifyDeclaration:
    @pytest.fixture
    def manifest(self) -> ProjectManifest:
        return ProjectManifest(
            name='demo',
            requires_python=None,
            build_backend=None,
            entry_points=(),
            classifiers=(),
            dependencies=('httpx',),
            dev_dependencies=('ruff',),
            optional_dependencies=('ty',),
        )

    @pytest.mark.parametrize(
        ('name', 'expected'),
        [
            pytest.param('httpx', Declaration.RUNTIME, id='runtime'),
            pytest.param('ruff', Declaration.DEVELOPMENT, id='development'),
            pytest.param('ty', Declaration.OPTIONAL, id='optional'),
            pytest.param('pytest', Declaration.UNDECLARED, id='undeclared'),
        ],
    )
    def test_the_first_group_naming_the_package_wins(
        self, manifest: ProjectManifest, name: str, expected: Declaration
    ) -> None:
        assert classify_declaration(manifest, name) == expected

    def test_without_a_manifest_nothing_is_declared(self) -> None:
        assert classify_declaration(NO_MANIFEST, 'ruff') == Declaration.UNDECLARED
