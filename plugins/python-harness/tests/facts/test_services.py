"""Workspace fact collection: ordering, counts, catalogs and unparsable files."""

from types import MappingProxyType

import pytest
from python_harness.core.tests.fixtures import ProjectBuilder
from python_harness.core.workspace import Workspace
from python_harness.facts.domain import FactKind, FactsReport
from python_harness.facts.services import (
    FactCatalog,
    build_full_catalog,
    build_review_catalog,
    collect_facts,
)
from python_harness.facts.tests.support import build_detector_catalog
from python_harness.facts.util.comments import (
    DOCSTRING_DETECTORS,
    collect_comment_facts,
)


class TestCollectFacts:
    FILES = MappingProxyType(
        {
            'pkg/loader.py': """
            # loader
            def load(items=[]):  # cache
                '''Return the items.'''
                return items


            del load
        """,
            'pkg/broken.py': 'def broken(:\n',
        }
    )
    EXPECTED_ORDER = (
        (1, FactKind.COMMENT),
        (2, FactKind.COMMENT),
        (2, FactKind.FUNCTION_SHAPE),
        (2, FactKind.MUTABLE_DEFAULT),
        (3, FactKind.DOCSTRING),
        (7, FactKind.DEL_STATEMENT),
    )
    EXPECTED_COUNTS = MappingProxyType(
        {
            FactKind.COMMENT: 2,
            FactKind.DEL_STATEMENT: 1,
            FactKind.DOCSTRING: 1,
            FactKind.FUNCTION_SHAPE: 1,
            FactKind.MUTABLE_DEFAULT: 1,
        }
    )

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    @pytest.fixture
    def report(self, workspace: Workspace) -> FactsReport:
        return collect_facts(workspace, ('pkg',))

    def test_facts_are_ordered_by_line_then_kind(self, report: FactsReport) -> None:
        loader = report.modules[0]

        ordered = tuple((fact.line, fact.detail.kind) for fact in loader.facts)
        assert ordered == self.EXPECTED_ORDER

    def test_counts_tally_each_kind(self, report: FactsReport) -> None:
        assert report.modules[0].counts == self.EXPECTED_COUNTS

    def test_unparsable_files_are_reported_beside_parsed_modules(self, report: FactsReport) -> None:
        parsed = tuple(module.path for module in report.modules)
        unparsable = tuple(item.path for item in report.unparsable)

        assert (parsed, unparsable) == (('pkg/loader.py',), ('pkg/broken.py',))

    @pytest.mark.parametrize(
        ('catalog', 'expected'),
        [
            pytest.param(
                build_detector_catalog(DOCSTRING_DETECTORS),
                frozenset({FactKind.DOCSTRING}),
                id='node-detectors-only',
            ),
            pytest.param(
                FactCatalog(node_detectors=(), module_collectors=(collect_comment_facts,)),
                frozenset({FactKind.COMMENT}),
                id='module-collectors-only',
            ),
        ],
    )
    def test_catalog_chooses_what_runs(
        self, workspace: Workspace, catalog: FactCatalog, expected: frozenset[FactKind]
    ) -> None:
        report = collect_facts(workspace, ('pkg',), catalog)

        assert frozenset(report.modules[0].counts) == expected

    def test_overlapping_paths_report_a_module_once(self, workspace: Workspace) -> None:
        report = collect_facts(workspace, ('pkg', 'pkg/loader.py'))

        assert tuple(module.path for module in report.modules) == ('pkg/loader.py',)


class TestCatalogs:
    FILES = MappingProxyType(
        {
            'pkg/shapes.py': """
                def build(value: int) -> int:
                    if value:
                        return value
                    return 0
            """,
        }
    )

    @pytest.fixture
    def workspace(self, project_builder: ProjectBuilder) -> Workspace:
        return project_builder.write(self.FILES)

    @pytest.mark.parametrize(
        ('catalog', 'expected'),
        [
            pytest.param(
                build_review_catalog(), frozenset(), id='review-catalog-leaves-out-shapes'
            ),
            pytest.param(
                build_full_catalog(),
                frozenset({FactKind.FUNCTION_SHAPE}),
                id='full-catalog-adds-shapes',
            ),
        ],
    )
    def test_only_the_full_catalog_emits_function_shapes(
        self, workspace: Workspace, catalog: FactCatalog, expected: frozenset[FactKind]
    ) -> None:
        report = collect_facts(workspace, ('pkg',), catalog)

        assert frozenset(report.modules[0].counts) == expected
