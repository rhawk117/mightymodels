"""The boundary cases of the measurement functions, each named after the input that sits on it."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mightymodels_mcp.review_metrics.components import package_of
from mightymodels_mcp.review_metrics.domain import FileMetric, FunctionMetric
from mightymodels_mcp.review_metrics.files import is_test_path
from mightymodels_mcp.review_metrics.python_source import analyze_python
from mightymodels_mcp.review_metrics.script_source import js_param_stats
from mightymodels_mcp.review_metrics.summary import LOC_RULE, PARAMS_RULE, violation_group

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_mcp.review_metrics.summary import Rule


def function_metric(name: str, *, loc: int = 1, params: int = 0) -> FunctionMetric:
    return FunctionMetric(
        file='m.py', name=name, line=1, loc=loc, params=params, bool_params=0, max_depth=0
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class PythonFile:
    name: str
    rel: str
    text: str
    expected: FileMetric
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def analyze_python_cases() -> pytest.MarkDecorator:
    syntax_error = PythonFile(
        name='syntax-error',
        rel='billing/broken.py',
        text='def broken(:\n    pass\n',
        expected=FileMetric(
            path='billing/broken.py', language='python', loc=2, long_lines=0, parsed=False
        ),
    )
    async_function = PythonFile(
        name='async-function',
        rel='billing/jobs.py',
        text='async def fetch(url, flag: bool):\n    return url\n',
        expected=FileMetric(
            path='billing/jobs.py',
            language='python',
            loc=2,
            long_lines=0,
            functions=(
                FunctionMetric(
                    file='billing/jobs.py',
                    name='fetch',
                    line=1,
                    loc=2,
                    params=2,
                    bool_params=1,
                    max_depth=0,
                ),
            ),
        ),
    )
    relative_import = PythonFile(
        name='relative-imports',
        rel='billing/io.py',
        text='from . import core\nfrom .util import helper\n',
        expected=FileMetric(
            path='billing/io.py',
            language='python',
            loc=2,
            long_lines=0,
            imports=('billing.core', 'billing.util.helper'),
        ),
    )
    init_relative = PythonFile(
        name='relative-imports-in-package-init',
        rel='pkg/sub/__init__.py',
        text='from .x import y\nfrom ..z import w\n',
        expected=FileMetric(
            path='pkg/sub/__init__.py',
            language='python',
            loc=2,
            long_lines=0,
            imports=('pkg.sub.x.y', 'pkg.z.w'),
        ),
    )
    deep_expression = PythonFile(
        name='deep-expression',
        rel='billing/deep.py',
        text='x = ' + '(' * 300 + '1' + ')' * 300 + '\n',
        expected=FileMetric(
            path='billing/deep.py', language='python', loc=1, long_lines=1, parsed=False
        ),
    )
    bool_pairing = PythonFile(
        name='bool-annotation-and-default-count-once',
        rel='billing/flags.py',
        text='def f(a: bool = False, b: int = 1):\n    return a\n',
        expected=FileMetric(
            path='billing/flags.py',
            language='python',
            loc=2,
            long_lines=0,
            functions=(
                FunctionMetric(
                    file='billing/flags.py',
                    name='f',
                    line=1,
                    loc=2,
                    params=2,
                    bool_params=1,
                    max_depth=0,
                ),
            ),
        ),
    )
    test_file = PythonFile(
        name='test-path-is-flagged',
        rel='tests/test_core.py',
        text='x = 1\n',
        expected=FileMetric(
            path='tests/test_core.py', language='python', loc=1, long_lines=0, is_test=True
        ),
    )
    return pytest.mark.parametrize(
        'source',
        [
            syntax_error.param,
            async_function.param,
            relative_import.param,
            init_relative.param,
            deep_expression.param,
            bool_pairing.param,
            test_file.param,
        ],
    )


def js_param_stats_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('raw', 'stats'),
        [
            pytest.param('', (0, 0), id='empty'),
            pytest.param('   ', (0, 0), id='blank'),
            pytest.param('a', (1, 0), id='one-parameter'),
            pytest.param('a, b, c', (3, 0), id='three-parameters'),
            pytest.param('a, {b, c}, [d, e]', (3, 0), id='commas-inside-brackets'),
            pytest.param('a, b = [1, 2]', (2, 0), id='default-array'),
            pytest.param('fill: boolean, scale = 1', (2, 1), id='typed-boolean'),
            pytest.param('a = true, b = false, c = 0', (3, 2), id='boolean-defaults'),
            pytest.param('flag: boolean = true', (1, 1), id='boolean-counted-once-at-most'),
            pytest.param('flag: boolean = true, b', (2, 1), id='boolean-typed-and-defaulted'),
            pytest.param('a: boolean = true, b = 1', (2, 1), id='boolean-then-number'),
            pytest.param(
                '{ retries = 3, verbose = false } = {}', (1, 1), id='destructured-with-boolean'
            ),
        ],
    )


def is_test_path_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('path', 'is_test'),
        [
            pytest.param('tests/core.py', True, id='tests-directory'),
            pytest.param('web/__tests__/util.js', True, id='dunder-tests-directory'),
            pytest.param('pkg/Specs/a.ts', True, id='directory-name-ignores-case'),
            pytest.param('pkg/test_core.py', True, id='test-prefix'),
            pytest.param('pkg/core_test.py', True, id='test-suffix'),
            pytest.param('pkg/conftest.py', True, id='conftest'),
            pytest.param('web/util.test.js', True, id='dot-test-infix'),
            pytest.param('web/util.spec.ts', True, id='dot-spec-infix'),
            pytest.param('src/billing/core.py', False, id='source-file'),
            pytest.param('tests.py', False, id='file-named-like-the-directory'),
            pytest.param('pkg/latest.py', False, id='name-ending-in-test-letters'),
            pytest.param('pkg/testing/core.py', False, id='directory-that-only-starts-with-test'),
        ],
    )


def package_of_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('module', 'depth', 'package'),
        [
            pytest.param('billing', 1, 'billing', id='single-part'),
            pytest.param('billing.core.io', 1, 'billing', id='default-depth'),
            pytest.param('billing.core.io', 2, 'billing.core', id='depth-two'),
            pytest.param('billing.core', 5, 'billing.core', id='depth-beyond-the-name'),
            pytest.param('billing.core', 0, 'billing', id='depth-zero-is-one'),
            pytest.param('src.billing.core', 1, 'billing', id='src-layout-prefix-dropped'),
            pytest.param('src.lib.billing.core', 2, 'billing.core', id='stacked-layout-prefixes'),
            pytest.param('src.billing', 1, 'billing', id='prefix-then-single-part'),
            pytest.param('src', 1, 'src', id='layout-name-alone-is-kept'),
            pytest.param('billing.src.core', 2, 'billing.src', id='layout-name-inside-is-kept'),
        ],
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class GroupCase:
    name: str
    rule: Rule
    functions: tuple[FunctionMetric, ...]
    cap: int
    count: int
    worst: tuple[str, ...]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def violation_group_cases() -> pytest.MarkDecorator:
    long_ones = (
        function_metric('twenty', loc=20),
        function_metric('twenty-one', loc=21),
        function_metric('thirty', loc=30),
        function_metric('forty', loc=40),
    )
    four_params = function_metric('four', params=4)
    three_params = function_metric('three', params=3)
    cases = [
        GroupCase(
            name='cap-below-the-hits',
            rule=LOC_RULE,
            functions=long_ones,
            cap=2,
            count=3,
            worst=('forty', 'thirty'),
        ),
        GroupCase(
            name='cap-equal-to-the-hits',
            rule=LOC_RULE,
            functions=long_ones,
            cap=3,
            count=3,
            worst=('forty', 'thirty', 'twenty-one'),
        ),
        GroupCase(
            name='cap-above-the-hits',
            rule=LOC_RULE,
            functions=long_ones,
            cap=10,
            count=3,
            worst=('forty', 'thirty', 'twenty-one'),
        ),
        GroupCase(
            name='cap-zero-keeps-the-count',
            rule=LOC_RULE,
            functions=long_ones,
            cap=0,
            count=3,
            worst=(),
        ),
        GroupCase(
            name='value-at-the-limit-is-not-a-hit',
            rule=PARAMS_RULE,
            functions=(three_params,),
            cap=5,
            count=0,
            worst=(),
        ),
        GroupCase(
            name='value-one-over-the-limit-is-a-hit',
            rule=PARAMS_RULE,
            functions=(three_params, four_params),
            cap=5,
            count=1,
            worst=('four',),
        ),
        GroupCase(name='no-functions', rule=LOC_RULE, functions=(), cap=5, count=0, worst=()),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestAnalyzePython:
    @analyze_python_cases()
    def test_the_file_measures_what_its_source_holds(self, source: PythonFile) -> None:
        assert analyze_python(Path(source.rel), source.text) == source.expected


class TestJsParamStats:
    @js_param_stats_cases()
    def test_count_and_booleans_of_a_parameter_list(self, raw: str, stats: tuple[int, int]) -> None:
        assert js_param_stats(raw) == stats


class TestIsTestPath:
    @is_test_path_cases()
    def test_the_path_is_or_is_not_a_test(self, path: str, is_test: bool) -> None:
        assert is_test_path(Path(path)) is is_test


class TestPackageOf:
    @package_of_cases()
    def test_the_module_belongs_to_the_package(self, module: str, depth: int, package: str) -> None:
        assert package_of(module, depth) == package


class TestViolationGroup:
    @violation_group_cases()
    def test_count_is_every_hit_and_worst_is_the_capped_ranking(self, case: GroupCase) -> None:
        group = violation_group(list(case.functions), case.rule, case.cap)

        assert (group.count, tuple(v.name for v in group.worst)) == (case.count, case.worst)
