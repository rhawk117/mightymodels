"""Manifest facts from a parsed pyproject.toml: backends and declared dependencies."""

import pytest
import tomllib
from python_harness.survey.domain import ProjectManifest
from python_harness.survey.util import LEGACY_BUILD_BACKEND, manifest_from_document


@pytest.fixture
def manifest(request: pytest.FixtureRequest) -> ProjectManifest:
    return manifest_from_document(tomllib.loads(request.param))


class TestManifestFromDocument:
    PYPROJECT = """
        [project]
        name = "Demo-App"
        requires-python = ">=3.14"
        classifiers = ["Typing :: Typed"]
        dependencies = [
            "SQLAlchemy>=2",
            "pydantic_settings[yaml]~=2.0",
            "msgspec ; python_version >= '3.14'",
        ]

        [project.scripts]
        demo-admin = "demo.cli:admin"
        demo = "demo.cli:main"

        [project.optional-dependencies]
        docs = ["MkDocs.Material"]

        [dependency-groups]
        dev = ["pytest>=9", {include-group = "lint"}]
        lint = ["ruff"]

        [tool.uv]
        dev-dependencies = ["Hypothesis"]

        [build-system]
        requires = ["uv_build"]
        build-backend = "uv_build"
    """
    EXPECTED = ProjectManifest(
        name='Demo-App',
        requires_python='>=3.14',
        build_backend='uv_build',
        entry_points=('demo', 'demo-admin'),
        classifiers=('Typing :: Typed',),
        dependencies=('msgspec', 'pydantic-settings', 'sqlalchemy'),
        dev_dependencies=('hypothesis', 'pytest', 'ruff'),
        optional_dependencies=('mkdocs-material',),
    )

    @pytest.mark.parametrize('manifest', [pytest.param(PYPROJECT, id='full')], indirect=True)
    def test_reads_declared_facts_with_normalized_names(self, manifest: ProjectManifest) -> None:
        assert manifest == self.EXPECTED


class TestPoetryDeclarations:
    PYPROJECT = """
        [tool.poetry.dependencies]
        python = "^3.12"
        Requests = "^2.32"

        [tool.poetry.dev-dependencies]
        black = "*"

        [tool.poetry.group.dev.dependencies]
        pytest = "^8"
        ruff = "*"

        [tool.poetry.group.docs]
        optional = true

        [tool.poetry.group.docs.dependencies]
        mkdocs = "*"
    """

    @pytest.mark.parametrize('manifest', [pytest.param(PYPROJECT, id='poetry')], indirect=True)
    def test_poetry_groups_count_like_their_pep_counterparts(
        self, manifest: ProjectManifest
    ) -> None:
        assert (
            manifest.dependencies,
            manifest.dev_dependencies,
            manifest.optional_dependencies,
        ) == (('requests',), ('black', 'pytest', 'ruff'), ('mkdocs',))


class TestBuildBackend:
    @pytest.mark.parametrize(
        ('manifest', 'expected'),
        [
            pytest.param(
                '[build-system]\nrequires = ["setuptools"]\n',
                LEGACY_BUILD_BACKEND,
                id='build-system-without-backend',
            ),
            pytest.param('[project]\nname = "demo"\n', None, id='no-build-system'),
        ],
        indirect=['manifest'],
    )
    def test_build_backend_follows_pep_517(
        self, manifest: ProjectManifest, expected: str | None
    ) -> None:
        assert manifest.build_backend == expected


class TestDefaultAndOptionalDependencies:
    @pytest.mark.parametrize(
        ('manifest', 'expected'),
        [
            pytest.param(
                """
                [dependency-groups]
                dev = ["pytest"]
                docs = ["mkdocs"]
                """,
                (('pytest',), ('mkdocs',)),
                id='dev-group-is-the-default',
            ),
            pytest.param(
                """
                [dependency-groups]
                dev = ["pytest"]
                lint = ["ruff"]

                [tool.uv]
                default-groups = ["lint"]
                """,
                (('ruff',), ('pytest',)),
                id='default-groups-list-replaces-dev',
            ),
            pytest.param(
                """
                [dependency-groups]
                dev = ["pytest"]
                docs = ["mkdocs"]

                [tool.uv]
                default-groups = "all"
                """,
                (('mkdocs', 'pytest'), ()),
                id='default-groups-all',
            ),
            pytest.param(
                """
                [tool.uv]
                dev-dependencies = ["pytest"]
                """,
                (('pytest',), ()),
                id='legacy-dev-dependencies',
            ),
            pytest.param(
                """
                [dependency-groups]
                docs = ["mkdocs"]

                [tool.uv]
                dev-dependencies = ["pytest"]
                default-groups = ["docs"]
                """,
                (('mkdocs',), ('pytest',)),
                id='legacy-dev-dependencies-follow-the-dev-group',
            ),
            pytest.param(
                """
                [dependency-groups]
                dev = [{include-group = "test"}]
                test = ["pytest"]
                """,
                (('pytest',), ()),
                id='group-included-by-a-default-group',
            ),
            pytest.param(
                """
                [dependency-groups]
                lint-tools = ["ruff"]

                [tool.uv]
                default-groups = ["Lint_Tools"]
                """,
                (('ruff',), ()),
                id='group-names-compare-normalized',
            ),
            pytest.param(
                """
                [dependency-groups]
                dev = ["pytest", {include-group = "lint"}]
                lint = ["ruff", {include-group = "dev"}]
                """,
                (('pytest', 'ruff'), ()),
                id='include-cycle-terminates',
            ),
            pytest.param(
                """
                [project.optional-dependencies]
                test = ["pytest"]
                """,
                ((), ('pytest',)),
                id='extras-are-optional',
            ),
        ],
        indirect=['manifest'],
    )
    def test_default_groups_are_dev_and_the_rest_are_optional(
        self,
        manifest: ProjectManifest,
        expected: tuple[tuple[str, ...], tuple[str, ...]],
    ) -> None:
        declared = (manifest.dev_dependencies, manifest.optional_dependencies)

        assert declared == expected


class TestDeclares:
    @pytest.mark.parametrize(
        ('manifest', 'expected'),
        [
            pytest.param('[project]\ndependencies = ["pytest"]\n', True, id='runtime-dependency'),
            pytest.param('[dependency-groups]\ndev = ["pytest"]\n', True, id='default-dev-group'),
            pytest.param(
                '[project.optional-dependencies]\ntest = ["pytest"]\n',
                False,
                id='extras-only',
            ),
            pytest.param(
                '[dependency-groups]\ntest = ["pytest"]\n',
                False,
                id='non-default-group-only',
            ),
        ],
        indirect=['manifest'],
    )
    def test_only_runtime_and_default_group_dependencies_are_declared(
        self, manifest: ProjectManifest, *, expected: bool
    ) -> None:
        assert manifest.declares('pytest') is expected
