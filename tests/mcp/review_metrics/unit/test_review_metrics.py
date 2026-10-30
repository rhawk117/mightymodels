"""The review metrics domain measuring a fixed tree and summarising what it found."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_mcp.review_metrics.components import build_module_graph
from mightymodels_mcp.review_metrics.domain import SummaryOptions
from mightymodels_mcp.review_metrics.sources import collect_metrics
from mightymodels_mcp.review_metrics.summary import render_summary, summarize

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from mightymodels_mcp.review_metrics.views import SummaryReport

LONG = 'x = "' + 'a' * 130 + '"'
CORE_PY = [
    'from abc import ABC, abstractmethod',
    'from . import io',
    '',
    '',
    'class Store(ABC):',
    '    @abstractmethod',
    '    def load(self): ...',
    '',
    '',
    'class Plain:',
    '    pass',
    '',
    '',
    'def busy(a, b, c, d, flag: bool = False, *rest, **extra):',
    '    for item in a:',
    '        if item:',
    '            while b:',
    '                b -= 1',
    '        elif c:',
    '            pass',
    *[f'    step_{n} = {n}' for n in range(20)],
    '    return io.write(a)',
    '',
    LONG,
]
IO_PY = [
    'from billing.core import Plain',
    'import os',
    '',
    '',
    'def write(value, verbose=True):',
    '    return Plain, os, value, verbose',
]
INDEX_TS = [
    "import { helper } from './util';",
    "export * from './shapes/index';",
    'export interface Shape { area(): number }',
    'export abstract class Base implements Shape {',
    '  abstract area(): number;',
    '}',
    'export class Square extends Base {',
    '  area(): number { return 4; }',
    '}',
    'export function draw(shape: Shape, fill: boolean, scale = 1, dry = false) {',
    '  if (fill) {',
    '    return helper(shape, scale, dry);',
    '  }',
    '  return null;',
    '}',
]
UTIL_JS = [
    "const lodash = require('lodash');",
    'const helper = (shape, scale, dry) => {',
    '  return lodash.identity([shape, scale, dry]);',
    '};',
    'async function load(url, { retries = 3, verbose = false } = {}) {',
    '  return fetch(url);',
    '}',
    'module.exports = { helper, load };',
]
SPEC_PY = ['from billing import core', '', '', 'def check():', '    return core']
CLI_PY = ['from billing.io import write', '', '', 'def run():', '    return write(1)']
UTIL_TEST_JS = ["const { helper } = require('./util');", "test('x', () => helper());"]
IGNORED_JS = ['function ignored(a,b,c,d,e){}']
SAMPLE: dict[str, list[str]] = {
    'src/billing/__init__.py': [],
    'src/billing/core.py': CORE_PY,
    'src/billing/io.py': IO_PY,
    'src/billing/spec/core_spec.py': SPEC_PY,
    'lib/tools/cli.py': CLI_PY,
    'web/index.ts': INDEX_TS,
    'web/shapes/index.ts': ["import { draw } from '../index';", 'export const unit = 1;'],
    'web/util.js': UTIL_JS,
    'web/util.test.js': UTIL_TEST_JS,
    'web/vendor.min.js': IGNORED_JS,
    'node_modules/dep/index.js': IGNORED_JS,
    '.hidden/skip.py': ['def ignored(a, b, c, d, e): ...'],
}


class TestSampleTreeReport:
    SUMMARY_LINES_AT_DEPTH_1 = (
        'files\t9 (2 test)',
        'source LOC\t68\ttest LOC\t5\tratio\t0.074',
        'module cycles (ADP)\t2',
        'package cycles (ADP)\t0',
        'functions > 20 LOC\t1',
        'functions > 3 params\t2',
        'functions with bool params\t4',
        'functions nested > 2\t1',
        'files > 500 LOC\t0',
        'lines > 120 chars\t1',
        '',
        'package\tCa\tCe\tI\tA\tD',
        'billing\t1\t0\t0.0\t0.5\t0.5',
        'tools\t0\t1\t1.0\tNone\tNone',
        'web\t0\t0\tNone\t0.667\tNone',
    )

    @pytest.fixture
    def sample(self, tmp_path: Path) -> Path:
        root = tmp_path.joinpath('sample')
        for name, lines in SAMPLE.items():
            path = root.joinpath(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return root

    @pytest.fixture
    def report_of(self, sample: Path) -> Callable[[int], SummaryReport]:
        def build(depth: int) -> SummaryReport:
            metrics = collect_metrics(sample)
            return summarize(metrics, build_module_graph(metrics), SummaryOptions(depth=depth))

        return build

    @pytest.mark.parametrize('depth', [1, 2])
    def test_the_report_counts_the_sample_tree(
        self, report_of: Callable[[int], SummaryReport], depth: int
    ) -> None:
        report = report_of(depth)

        assert report.tool == 'review_metrics'
        assert (report.totals.files, report.totals.source_files, report.totals.test_files) == (
            9,
            7,
            2,
        )
        assert set(report.totals.loc_by_language) == {'python', 'typescript', 'javascript'}

    def test_the_report_lists_what_breaks_a_limit(
        self, report_of: Callable[[int], SummaryReport]
    ) -> None:
        violations = report_of(1).violations

        assert [v.name for v in violations.functions_over_3_params.worst] == ['busy', 'draw']
        assert [v.name for v in violations.functions_over_20_loc.worst] == ['busy']
        assert violations.functions_with_bool_params.count == 4
        assert violations.functions_nested_deeper_than_2.count == 1
        assert violations.long_lines_over_120_chars == 1

    def test_the_package_depth_changes_the_packages_listed(
        self,
        report_of: Callable[[int], SummaryReport],
    ) -> None:
        shallow = report_of(1).component_metrics.packages
        deep = report_of(2).component_metrics.packages

        assert set(shallow) == {'tools', 'billing', 'web'}
        assert set(deep) != set(shallow)

    def test_the_summary_text_names_the_report_headline(
        self,
        report_of: Callable[[int], SummaryReport],
    ) -> None:
        text = render_summary(report_of(1))

        assert tuple(text.splitlines()) == self.SUMMARY_LINES_AT_DEPTH_1
