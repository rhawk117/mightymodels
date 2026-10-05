"""Mode inference rules and domain detection from names and layout."""

from dataclasses import replace
from types import MappingProxyType

import pytest
from python_harness.survey.domain import (
    Domain,
    LayoutFacts,
    Mode,
    ModeInference,
    ProjectManifest,
    SurveyOptions,
)
from python_harness.survey.policy import detect_domains, infer_mode

LIBRARY_MANIFEST = ProjectManifest(
    name='demo',
    requires_python='>=3.14',
    build_backend='uv_build',
    entry_points=(),
    classifiers=(),
    dependencies=(),
    dev_dependencies=(),
    optional_dependencies=(),
)
PLAIN_LAYOUT = LayoutFacts(
    has_py_typed=False,
    has_dunder_main=False,
    has_src_layout=True,
    has_tests_directory=False,
    has_uv_lock=False,
)


class TestInferMode:
    LIBRARY_REASON = 'build backend uv_build without entry points'

    @pytest.mark.parametrize(
        ('manifest', 'layout', 'expected'),
        [
            pytest.param(
                None,
                replace(PLAIN_LAYOUT, has_py_typed=True),
                ModeInference(Mode.APPLICATION, ('no pyproject.toml',)),
                id='no-manifest',
            ),
            pytest.param(
                replace(LIBRARY_MANIFEST, entry_points=('demo', 'demo-admin')),
                PLAIN_LAYOUT,
                ModeInference(Mode.APPLICATION, ('entry points: demo, demo-admin',)),
                id='entry-points-outrank-build-backend',
            ),
            pytest.param(
                LIBRARY_MANIFEST,
                replace(PLAIN_LAYOUT, has_dunder_main=True),
                ModeInference(Mode.APPLICATION, ('__main__.py present',)),
                id='dunder-main',
            ),
            pytest.param(
                replace(LIBRARY_MANIFEST, build_backend=None),
                PLAIN_LAYOUT,
                ModeInference(Mode.APPLICATION, ('no build backend: uv application layout',)),
                id='no-build-backend',
            ),
            pytest.param(
                LIBRARY_MANIFEST,
                PLAIN_LAYOUT,
                ModeInference(Mode.LIBRARY, (LIBRARY_REASON,)),
                id='build-backend-only',
            ),
            pytest.param(
                replace(LIBRARY_MANIFEST, classifiers=('Typing :: Typed',)),
                replace(PLAIN_LAYOUT, has_py_typed=True),
                ModeInference(
                    Mode.LIBRARY,
                    (
                        LIBRARY_REASON,
                        'py.typed marker present',
                        'Typing :: Typed classifier',
                    ),
                ),
                id='typed-library',
            ),
        ],
    )
    def test_first_matching_rule_decides_with_its_evidence(
        self,
        manifest: ProjectManifest | None,
        layout: LayoutFacts,
        expected: ModeInference,
    ) -> None:
        assert infer_mode(manifest, layout) == expected


class TestDetectDomains:
    CUSTOM_OPTIONS = SurveyOptions(
        domain_markers=MappingProxyType({Domain.MCP: frozenset({'modelcontextprotocol'})})
    )

    @pytest.mark.parametrize(
        ('manifest', 'expected'),
        [
            pytest.param(
                replace(LIBRARY_MANIFEST, dependencies=('fastapi', 'sqlmodel')),
                (Domain.SQLALCHEMY, Domain.FASTAPI),
                id='runtime-dependencies',
            ),
            pytest.param(
                replace(LIBRARY_MANIFEST, dev_dependencies=('hypothesis', 'pytest')),
                (Domain.PYTEST, Domain.HYPOTHESIS),
                id='dev-dependencies',
            ),
            pytest.param(
                replace(LIBRARY_MANIFEST, optional_dependencies=('hypothesis',)),
                (Domain.HYPOTHESIS,),
                id='optional-dependencies',
            ),
            pytest.param(
                replace(LIBRARY_MANIFEST, dependencies=('pydantic-settings',)),
                (Domain.PYDANTIC,),
                id='normalized-distribution-name',
            ),
        ],
    )
    def test_declared_distributions_mark_domains(
        self, manifest: ProjectManifest, expected: tuple[Domain, ...]
    ) -> None:
        assert detect_domains(manifest, (), PLAIN_LAYOUT) == expected

    @pytest.mark.parametrize(
        ('external_packages', 'expected'),
        [
            pytest.param(
                ('json', 'asyncio', 'argparse'),
                (Domain.CLI, Domain.ASYNCIO),
                id='standard-library-imports',
            ),
            pytest.param(
                ('pydantic_settings', 'msgspec', 'mcp'),
                (Domain.MCP, Domain.PYDANTIC, Domain.MSGSPEC),
                id='third-party-import-names',
            ),
            pytest.param(('json', 'requests'), (), id='nothing-recognised'),
        ],
    )
    def test_imported_packages_mark_domains(
        self, external_packages: tuple[str, ...], expected: tuple[Domain, ...]
    ) -> None:
        assert detect_domains(None, external_packages, PLAIN_LAYOUT) == expected

    @pytest.mark.parametrize(
        ('manifest', 'layout', 'expected'),
        [
            pytest.param(
                None,
                replace(PLAIN_LAYOUT, has_tests_directory=True),
                (Domain.PYTEST,),
                id='tests-directory',
            ),
            pytest.param(
                replace(LIBRARY_MANIFEST, entry_points=('demo',)),
                PLAIN_LAYOUT,
                (Domain.CLI,),
                id='entry-points',
            ),
        ],
    )
    def test_layout_and_entry_points_mark_domains(
        self,
        manifest: ProjectManifest | None,
        layout: LayoutFacts,
        expected: tuple[Domain, ...],
    ) -> None:
        assert detect_domains(manifest, (), layout) == expected

    def test_marker_table_comes_from_the_options(self) -> None:
        domains = detect_domains(
            None,
            ('modelcontextprotocol', 'pytest'),
            PLAIN_LAYOUT,
            options=self.CUSTOM_OPTIONS,
        )

        assert domains == (Domain.MCP,)
