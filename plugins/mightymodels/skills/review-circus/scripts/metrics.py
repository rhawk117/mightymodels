"""Deterministic code metrics for review-circus's uncle-bob-reviewer.

Computes the mechanical layer of a Robert C. Martin code-quality review:

- Function size, parameter counts, boolean flag parameters, nesting depth
  (Clean Code ch. 3; smells F1, F3)
- File size and long lines (Clean Code ch. 5)
- Martin's component metrics: fan-in (Ca), fan-out (Ce), Instability
  I = Ce/(Ca+Ce), Abstractness A, Distance from the Main Sequence
  D = |A + I - 1| (Agile PPP / Clean Architecture chs. 13-14)
- Dependency cycles (Acyclic Dependencies Principle) via Tarjan SCC
- Test presence and test-to-source LOC ratio

Stdlib only, Python 3.12. Python is parsed with ast (reliable). JS/TS is
parsed with regex heuristics: the import graph is reliable, function-level
numbers are approximate and marked as such in the output.

Usage:
    python3 metrics.py <repo_root> [--out metrics.json] [--max-listed 50]
        [--package-depth N]
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

IGNORED_DIRS = {
    '.git',
    '.hg',
    '.svn',
    'node_modules',
    '__pycache__',
    '.venv',
    'venv',
    'env',
    '.tox',
    '.mypy_cache',
    '.ruff_cache',
    '.pytest_cache',
    'dist',
    'build',
    '.next',
    '.nuxt',
    'coverage',
    'vendor',
    'target',
    '.idea',
    '.vscode',
    'site-packages',
    '.eggs',
}
PY_SUFFIXES = {'.py'}
JS_SUFFIXES = {'.js', '.jsx', '.mjs', '.cjs'}
TS_SUFFIXES = {'.ts', '.tsx', '.mts', '.cts'}
LINE_LIMIT = 120
FUNCTION_LOC_LIMIT = 20
PARAM_LIMIT = 3
FILE_LOC_LIMIT = 500
DEPTH_LIMIT = 2
MIN_CAPTURE_GROUPS = 2
LAYOUT_DIRS = ('src', 'lib', 'app')
SRC_PREFIX = 'src.'
TEST_DIR_NAMES = {'test', 'tests', '__tests__', 'spec', 'specs'}
_LOGGER = logging.getLogger(__name__)

JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*{},\s$]+\s+from\s+)?|export\s+[\w*{},\s$]+\s+from\s+|"""
    r"""require\(\s*|import\(\s*)['"]([^'"]+)['"]"""
)
JS_FUNC_RES = (
    re.compile(
        r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([\w$]+)?\s*\(([^)]*)\)'
    ),
    re.compile(
        r'^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s+)?(?:function\s*\*?\s*)?\(([^)]*)\)\s*(?:=>|\{)'
    ),
    re.compile(r'^\s*(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s+)?([\w$]+)\s*=>'),
)
TS_ABSTRACT_RE = re.compile(
    r'^\s*(?:export\s+)?(?:declare\s+)?(?:abstract\s+class|interface)\s+[\w$]+',
    re.MULTILINE,
)
TS_CLASS_RE = re.compile(
    r'^\s*(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?class\s+[\w$]+', re.MULTILINE
)


@dataclass(slots=True)
class FunctionMetric:
    file: str
    name: str
    line: int
    loc: int
    params: int
    bool_params: int
    max_depth: int
    approximate: bool = False


@dataclass(slots=True)
class FileMetric:
    path: str
    language: str
    loc: int
    long_lines: int
    classes: int = 0
    abstract_classes: int = 0
    is_test: bool = False
    functions: list[FunctionMetric] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SummaryOptions:
    cap: int = 50
    depth: int = 1


DEFAULT_SUMMARY_OPTIONS = SummaryOptions()


class PackageMetric(TypedDict):
    modules: int
    classes: int
    abstract_classes: int
    loc: int
    fan_in_ca: int
    fan_out_ce: int
    instability_i: float | None
    abstractness_a: float | None
    distance_d: float | None


class PackageReport(TypedDict):
    packages: dict[str, PackageMetric]
    package_cycles: list[list[str]]


class Violation(TypedDict):
    file: str
    name: str
    line: int
    loc: int
    params: int
    bool_params: int
    max_depth: int
    approximate: bool


class ViolationGroup(TypedDict):
    count: int
    worst: list[Violation]


class FileViolation(TypedDict):
    file: str
    loc: int


class Violations(TypedDict):
    functions_over_20_loc: ViolationGroup
    functions_over_3_params: ViolationGroup
    functions_with_bool_params: ViolationGroup
    functions_nested_deeper_than_2: ViolationGroup
    files_over_500_loc: list[FileViolation]
    long_lines_over_120_chars: int


class Totals(TypedDict):
    files: int
    source_files: int
    test_files: int
    source_loc: int
    test_loc: int
    test_to_source_ratio: float | None
    functions_measured: int
    loc_by_language: dict[str, int]


class ModuleCycles(TypedDict):
    count: int
    cycles: list[list[str]]


class SummaryReport(TypedDict):
    tool: str
    granularity_note: str
    totals: Totals
    component_metrics: PackageReport
    module_cycles_adp: ModuleCycles
    violations: Violations


def language_of(path: Path) -> str | None:
    if path.suffix in PY_SUFFIXES:
        return 'python'
    if path.suffix in JS_SUFFIXES:
        return 'javascript'
    if path.suffix in TS_SUFFIXES:
        return 'typescript'
    return None


def is_test_path(rel: Path) -> bool:
    parts = {p.lower() for p in rel.parts[:-1]}
    if parts & TEST_DIR_NAMES:
        return True
    stem = rel.stem.lower()
    if stem.startswith('test_') or stem.endswith('_test') or stem == 'conftest':
        return True
    return any(marker in rel.name.lower() for marker in ('.spec.', '.test.'))


def iter_source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or language_of(path) is None:
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS or part.startswith('.') for part in rel_parts[:-1]):
            continue
        if path.name.endswith(('.min.js', '.bundle.js', '.d.ts')):
            continue
        found.append(path)
    return found


def count_loc(text: str) -> tuple[int, int]:
    loc = 0
    long_lines = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        loc += 1
        if len(line) > LINE_LIMIT:
            long_lines += 1
    return loc, long_lines


def python_param_stats(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, int]:
    args = node.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    named = [a for a in params if a.arg not in ('self', 'cls')]
    bool_count = 0
    defaults = [*args.defaults, *args.kw_defaults]
    for default in defaults:
        if isinstance(default, ast.Constant) and isinstance(default.value, bool):
            bool_count += 1
    for arg in named:
        annotation = getattr(arg, 'annotation', None)
        if isinstance(annotation, ast.Name) and annotation.id == 'bool':
            bool_count += 1
    extra = (1 if args.vararg else 0) + (1 if args.kwarg else 0)
    return len(named) + extra, min(bool_count, len(named))


SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
NESTING_NODES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
)


def dispatch_depth(child: ast.AST, depth: int) -> int:
    if isinstance(child, SCOPE_NODES):
        return depth
    if isinstance(child, ast.If):
        return if_chain_depth(child, depth + 1)
    if isinstance(child, NESTING_NODES):
        return python_max_depth(child, depth + 1)
    return python_max_depth(child, depth)


def python_max_depth(node: ast.AST, depth: int = 0) -> int:
    deepest = depth
    for child in ast.iter_child_nodes(node):
        deepest = max(deepest, dispatch_depth(child, depth))
    return deepest


def if_chain_depth(node: ast.If, depth: int) -> int:
    """Depth of an if/elif chain; elif arms continue at the same depth."""
    deepest = depth
    for stmt in node.body:
        deepest = max(deepest, dispatch_depth(stmt, depth))
    if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
        return max(deepest, if_chain_depth(node.orelse[0], depth))
    for stmt in node.orelse:
        deepest = max(deepest, dispatch_depth(stmt, depth))
    return deepest


def _ast_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ''


def _has_abstract_method(node: ast.ClassDef) -> bool:
    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(
            _ast_name(decorator) in ('abstractmethod', 'abstractproperty')
            for decorator in item.decorator_list
        ):
            return True
    return False


def class_is_abstract(node: ast.ClassDef) -> bool:
    if any(_ast_name(base) in ('ABC', 'Protocol', 'ABCMeta') for base in node.bases):
        return True
    if any(keyword.arg == 'metaclass' for keyword in node.keywords):
        return True
    return _has_abstract_method(node)


def import_names(node: ast.AST, package_parts: list[str]) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return from_import_names(node, package_parts)
    return []


def python_imports(tree: ast.Module, module: str) -> list[str]:
    package_parts = module.split('.')[:-1]
    return [name for node in ast.walk(tree) for name in import_names(node, package_parts)]


def from_import_base(node: ast.ImportFrom, package_parts: list[str]) -> str:
    if node.level == 0:
        return node.module or ''
    prefix = '.'.join(package_parts[: len(package_parts) - node.level + 1])
    return '.'.join(filter(None, (prefix, node.module)))


def from_import_names(node: ast.ImportFrom, package_parts: list[str]) -> list[str]:
    base = from_import_base(node, package_parts)
    names = [alias.name for alias in node.names if alias.name != '*']
    if not names:
        return [base] if base else []
    return ['.'.join(filter(None, (base, name))) for name in names]


def analyze_python(_path: Path, rel: Path, text: str) -> FileMetric:
    loc, long_lines = count_loc(text)
    metric = FileMetric(str(rel), 'python', loc, long_lines, is_test=is_test_path(rel))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return metric
    metric.imports = python_imports(tree, module_name_for(rel))
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    metric.classes = len(classes)
    metric.abstract_classes = sum(1 for node in classes if class_is_abstract(node))
    metric.functions = [
        python_function(node, rel)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return metric


def python_function(node: ast.FunctionDef | ast.AsyncFunctionDef, rel: Path) -> FunctionMetric:
    params, bool_params = python_param_stats(node)
    end = getattr(node, 'end_lineno', node.lineno)
    return FunctionMetric(
        str(rel),
        node.name,
        node.lineno,
        end - node.lineno + 1,
        params,
        bool_params,
        python_max_depth(node),
    )


def js_function_end(lines: list[str], start: int) -> int:
    depth = 0
    opened = False
    for idx in range(start, len(lines)):
        line = lines[idx]
        depth += line.count('{') - line.count('}')
        opened = opened or '{' in line
        if opened and depth <= 0:
            return idx
        if not opened and line.rstrip().endswith((';', ',')) and idx > start:
            return idx
    return min(start + 1, len(lines) - 1)


def js_param_stats(raw: str) -> tuple[int, int]:
    raw = raw.strip()
    if not raw:
        return 0, 0
    depth = 0
    count = 1
    for char in raw:
        if char in '([{<':
            depth += 1
        elif char in ')]}>':
            depth -= 1
        elif char == ',' and depth == 0:
            count += 1
    bools = len(re.findall(r'(?:=\s*(?:true|false)\b|:\s*boolean\b)', raw))
    return count, min(bools, count)


def analyze_js(_path: Path, rel: Path, text: str, language: str) -> FileMetric:
    loc, long_lines = count_loc(text)
    metric = FileMetric(str(rel), language, loc, long_lines, is_test=is_test_path(rel))
    metric.imports = JS_IMPORT_RE.findall(text)
    if language == 'typescript':
        metric.classes = len(TS_CLASS_RE.findall(text)) + len(
            re.findall(r'^\s*(?:export\s+)?interface\s+[\w$]+', text, re.MULTILINE)
        )
        metric.abstract_classes = len(TS_ABSTRACT_RE.findall(text))
    lines = text.splitlines()
    found = (js_function(lines, idx, rel) for idx in range(len(lines)))
    metric.functions = [function for function in found if function is not None]
    return metric


def js_signature(line: str) -> re.Match[str] | None:
    return next(filter(None, (pattern.match(line) for pattern in JS_FUNC_RES)), None)


def js_function(lines: list[str], idx: int, rel: Path) -> FunctionMetric | None:
    match = js_signature(lines[idx])
    if match is None:
        return None
    captured = match.lastindex and match.lastindex >= MIN_CAPTURE_GROUPS
    params, bool_params = js_param_stats((match.group(2) if captured else '') or '')
    end = js_function_end(lines, idx)
    return FunctionMetric(
        str(rel),
        match.group(1) or '<anonymous>',
        idx + 1,
        end - idx + 1,
        params,
        bool_params,
        -1,
        approximate=True,
    )


def module_name_for(rel: Path) -> str:
    parts = list(rel.parts)
    parts[-1] = rel.stem
    if parts[-1] in ('__init__', 'index'):
        parts = parts[:-1]
    return '.'.join(parts) if parts else rel.stem


def package_of(module: str, depth: int = 1) -> str:
    parts = module.split('.')
    while len(parts) > 1 and parts[0] in LAYOUT_DIRS:
        parts = parts[1:]
    return '.'.join(parts[: max(depth, 1)]) if len(parts) > 1 else parts[0]


def module_lookup(names: list[str]) -> dict[str, str]:
    lookup = {name: name for name in names}
    for name in names:
        if name.startswith(SRC_PREFIX):
            lookup.setdefault(name.removeprefix(SRC_PREFIX), name)
    return lookup


def build_module_graph(metrics: list[FileMetric]) -> dict[str, set[str]]:
    names = [module_name_for(Path(m.path)) for m in metrics]
    lookup = module_lookup(names)
    graph: dict[str, set[str]] = {name: set() for name in names}
    for metric, source in zip(metrics, names, strict=True):
        targets = {resolve_internal(imp, metric, lookup) for imp in metric.imports}
        graph[source] |= {target for target in targets if target and target != source}
    return graph


def _resolve_python_internal(imp: str, lookup: dict[str, str]) -> str | None:
    candidate = imp
    while candidate:
        if candidate in lookup:
            return lookup[candidate]
        candidate = candidate.rpartition('.')[0]
    return None


def normalized_parts(parts: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for part in parts:
        if part == '..':
            normalized = normalized[:-1]
        elif part not in {'.', ''}:
            normalized.append(part)
    return normalized


def _resolve_javascript_internal(
    imp: str, metric: FileMetric, lookup: dict[str, str]
) -> str | None:
    if not imp.startswith('.'):
        return None
    joined = Path(metric.path).parent.joinpath(imp)
    if joined.suffix in JS_SUFFIXES | TS_SUFFIXES:
        joined = joined.with_suffix('')
    parts = normalized_parts(joined.parts)
    if parts and parts[-1] == 'index':
        parts = parts[:-1]
    return lookup.get('.'.join(parts))


def resolve_internal(imp: str, metric: FileMetric, lookup: dict[str, str]) -> str | None:
    if metric.language == 'python':
        return _resolve_python_internal(imp, lookup)
    return _resolve_javascript_internal(imp, metric, lookup)


@dataclass(slots=True)
class _TarjanState:
    graph: dict[str, set[str]]
    index_counter: int = 0
    stack: list[str] = field(default_factory=list)
    lowlinks: dict[str, int] = field(default_factory=dict)
    index: dict[str, int] = field(default_factory=dict)
    on_stack: dict[str, bool] = field(default_factory=dict)
    sccs: list[list[str]] = field(default_factory=list)

    def advance(
        self,
        current: str,
        children: Iterator[str],
        worklist: list[tuple[str, Iterator[str]]],
    ) -> bool:
        for child in children:
            if child not in self.index:
                self.index[child] = self.lowlinks[child] = self.index_counter
                self.index_counter += 1
                self.stack.append(child)
                self.on_stack[child] = True
                worklist.append((child, iter(sorted(self.graph.get(child, ())))))
                return True
            if self.on_stack.get(child):
                self.lowlinks[current] = min(self.lowlinks[current], self.index[child])
        return False

    def complete(self, worklist: list[tuple[str, Iterator[str]]]) -> None:
        current = worklist.pop()[0]
        if worklist:
            parent = worklist[-1][0]
            self.lowlinks[parent] = min(self.lowlinks[parent], self.lowlinks[current])
        if self.lowlinks[current] != self.index[current]:
            return
        component: list[str] = []
        while True:
            member = self.stack.pop()
            self.on_stack[member] = False
            component.append(member)
            if member == current:
                break
        self.sccs.append(sorted(component))

    def visit(self, node: str) -> None:
        worklist = [(node, iter(sorted(self.graph.get(node, ()))))]
        self.index[node] = self.lowlinks[node] = self.index_counter
        self.index_counter += 1
        self.stack.append(node)
        self.on_stack[node] = True
        while worklist:
            current, children = worklist[-1]
            if self.advance(current, children, worklist):
                continue
            self.complete(worklist)


def tarjan_sccs(graph: dict[str, set[str]]) -> list[list[str]]:
    state = _TarjanState(graph)
    for node in sorted(graph):
        if node not in state.index:
            state.visit(node)
    return [scc for scc in state.sccs if len(scc) > 1]


def _package_edges(graph: dict[str, set[str]], depth: int) -> set[tuple[str, str]]:
    pairs = {
        (package_of(source, depth), package_of(target, depth))
        for source, targets in graph.items()
        for target in targets
    }
    return {(source, target) for source, target in pairs if source != target}


def _package_totals(metrics: list[FileMetric], depth: int) -> dict[str, PackageMetric]:
    packages: dict[str, PackageMetric] = {}
    for metric in metrics:
        package = packages.setdefault(
            package_of(module_name_for(Path(metric.path)), depth),
            {
                'modules': 0,
                'classes': 0,
                'abstract_classes': 0,
                'loc': 0,
                'fan_in_ca': 0,
                'fan_out_ce': 0,
                'instability_i': None,
                'abstractness_a': None,
                'distance_d': None,
            },
        )
        package['modules'] += 1
        package['classes'] += metric.classes
        package['abstract_classes'] += metric.abstract_classes
        package['loc'] += metric.loc
    return packages


def _add_package_metrics(packages: dict[str, PackageMetric], edges: set[tuple[str, str]]) -> None:
    for name, package in packages.items():
        ce = sum(1 for source, _ in edges if source == name)
        ca = sum(1 for _, target in edges if target == name)
        instability = round(ce / (ca + ce), 3) if (ca + ce) else None
        abstractness = (
            round(package['abstract_classes'] / package['classes'], 3)
            if package['classes']
            else None
        )
        distance = None
        if instability is not None and abstractness is not None:
            distance = round(abs(abstractness + instability - 1), 3)
        package['fan_in_ca'] = ca
        package['fan_out_ce'] = ce
        package['instability_i'] = instability
        package['abstractness_a'] = abstractness
        package['distance_d'] = distance


def _package_graph(edges: set[tuple[str, str]]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for source, target in edges:
        graph.setdefault(source, set()).add(target)
        graph.setdefault(target, set())
    return graph


def package_metrics(
    graph: dict[str, set[str]], metrics: list[FileMetric], depth: int = 1
) -> PackageReport:
    edges = _package_edges(graph, depth)
    packages = _package_totals(metrics, depth)
    _add_package_metrics(packages, edges)
    return {'packages': packages, 'package_cycles': tarjan_sccs(_package_graph(edges))}


def function_loc(function: FunctionMetric) -> int:
    return function.loc


def function_params(function: FunctionMetric) -> int:
    return function.params


def function_bool_params(function: FunctionMetric) -> int:
    return function.bool_params


def function_depth(function: FunctionMetric) -> int:
    return function.max_depth


def file_loc(metric: FileMetric) -> int:
    return metric.loc


def violation(function: FunctionMetric) -> Violation:
    return {
        'file': function.file,
        'name': function.name,
        'line': function.line,
        'loc': function.loc,
        'params': function.params,
        'bool_params': function.bool_params,
        'max_depth': function.max_depth,
        'approximate': function.approximate,
    }


@dataclass(frozen=True, slots=True)
class Rule:
    measure: Callable[[FunctionMetric], int]
    limit: int


RULES: dict[str, Rule] = {
    'functions_over_20_loc': Rule(function_loc, FUNCTION_LOC_LIMIT),
    'functions_over_3_params': Rule(function_params, PARAM_LIMIT),
    'functions_with_bool_params': Rule(function_bool_params, 0),
    'functions_nested_deeper_than_2': Rule(function_depth, DEPTH_LIMIT),
}


def violation_group(functions: list[FunctionMetric], rule: Rule, cap: int) -> ViolationGroup:
    hits = [function for function in functions if rule.measure(function) > rule.limit]
    ranked = sorted(hits, key=rule.measure, reverse=True)[:cap]
    return {'count': len(hits), 'worst': [violation(function) for function in ranked]}


def collect_violations(metrics: list[FileMetric], cap: int) -> Violations:
    functions = [f for m in metrics for f in m.functions]
    groups = {name: violation_group(functions, rule, cap) for name, rule in RULES.items()}
    big_files = sorted((m for m in metrics if m.loc > FILE_LOC_LIMIT), key=file_loc, reverse=True)
    return {
        'functions_over_20_loc': groups['functions_over_20_loc'],
        'functions_over_3_params': groups['functions_over_3_params'],
        'functions_with_bool_params': groups['functions_with_bool_params'],
        'functions_nested_deeper_than_2': groups['functions_nested_deeper_than_2'],
        'files_over_500_loc': [{'file': m.path, 'loc': m.loc} for m in big_files[:cap]],
        'long_lines_over_120_chars': sum(m.long_lines for m in metrics),
    }


def totals_of(metrics: list[FileMetric]) -> Totals:
    src_loc = sum(m.loc for m in metrics if not m.is_test)
    test_loc = sum(m.loc for m in metrics if m.is_test)
    test_files = sum(1 for m in metrics if m.is_test)
    langs: dict[str, int] = {}
    for metric in metrics:
        langs[metric.language] = langs.get(metric.language, 0) + metric.loc
    return {
        'files': len(metrics),
        'source_files': len(metrics) - test_files,
        'test_files': test_files,
        'source_loc': src_loc,
        'test_loc': test_loc,
        'test_to_source_ratio': round(test_loc / src_loc, 3) if src_loc else None,
        'functions_measured': sum(len(m.functions) for m in metrics),
        'loc_by_language': langs,
    }


def summarize(
    metrics: list[FileMetric],
    graph: dict[str, set[str]],
    options: SummaryOptions = DEFAULT_SUMMARY_OPTIONS,
) -> SummaryReport:
    module_cycles = tarjan_sccs(graph)
    return {
        'tool': 'uncle-bob metrics.py',
        'granularity_note': (
            'fan-in/fan-out counted at module level, rolled up to top-level packages'
        ),
        'totals': totals_of(metrics),
        'component_metrics': package_metrics(graph, metrics, options.depth),
        'module_cycles_adp': {
            'count': len(module_cycles),
            'cycles': [c[:20] for c in module_cycles[: options.cap]],
        },
        'violations': collect_violations(metrics, options.cap),
    }


def render_summary(report: SummaryReport) -> str:
    totals = report['totals']
    violations = report['violations']
    lines = [
        f'files\t{totals["files"]} ({totals["test_files"]} test)',
        (
            f'source LOC\t{totals["source_loc"]}\ttest LOC\t{totals["test_loc"]}'
            f'\tratio\t{totals["test_to_source_ratio"]}'
        ),
        f'module cycles (ADP)\t{report["module_cycles_adp"]["count"]}',
        f'package cycles (ADP)\t{len(report["component_metrics"]["package_cycles"])}',
        (f'functions > {FUNCTION_LOC_LIMIT} LOC\t{violations["functions_over_20_loc"]["count"]}'),
        (f'functions > {PARAM_LIMIT} params\t{violations["functions_over_3_params"]["count"]}'),
        (f'functions with bool params\t{violations["functions_with_bool_params"]["count"]}'),
        (
            f'functions nested > {DEPTH_LIMIT}\t'
            f'{violations["functions_nested_deeper_than_2"]["count"]}'
        ),
        f'files > {FILE_LOC_LIMIT} LOC\t{len(violations["files_over_500_loc"])}',
        f'lines > {LINE_LIMIT} chars\t{violations["long_lines_over_120_chars"]}',
        '',
        'package\tCa\tCe\tI\tA\tD',
    ]
    for name, pkg in sorted(report['component_metrics']['packages'].items()):
        lines.append(
            f'{name}\t{pkg["fan_in_ca"]}\t{pkg["fan_out_ce"]}\t'
            f'{pkg["instability_i"]}\t{pkg["abstractness_a"]}\t{pkg["distance_d"]}'
        )
    return '\n'.join(lines)


def _read_source(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError as error:
        _LOGGER.debug('Unable to read source file %s', path, exc_info=error)
        return None


def _collect_metrics(root: Path) -> list[FileMetric]:
    metrics: list[FileMetric] = []
    for path in iter_source_files(root):
        text = _read_source(path)
        if text is None:
            continue
        rel = path.relative_to(root)
        language = language_of(path)
        if language == 'python':
            metrics.append(analyze_python(path, rel, text))
        elif language is not None:
            metrics.append(analyze_js(path, rel, text, language))
    return metrics


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description='Uncle Bob mechanical code metrics')
    root.add_argument('root', type=Path)
    root.add_argument('--out', type=Path, default=None)
    root.add_argument('--max-listed', type=int, default=50)
    root.add_argument(
        '--package-depth',
        type=int,
        default=1,
        help='path components per component rollup; use 2+ for single-package repos',
    )
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        sys.stderr.write(f'error: {root} is not a directory\n')
        return 2
    metrics = _collect_metrics(root)
    report = summarize(
        metrics,
        build_module_graph(metrics),
        SummaryOptions(cap=args.max_listed, depth=args.package_depth),
    )
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, sort_keys=False))
        sys.stdout.write(f'wrote {args.out}\n')
    sys.stdout.write(render_summary(report) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
