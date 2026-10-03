#!/usr/bin/env python3
"""Deterministic code metrics for the uncle-bob skill.

Computes the mechanical layer of a Robert C. Martin code-quality review:

- Function size, parameter counts, boolean flag parameters, nesting depth
  (Clean Code ch. 3; smells F1, F3)
- File size and long lines (Clean Code ch. 5)
- Martin's component metrics: fan-in (Ca), fan-out (Ce), Instability
  I = Ce/(Ca+Ce), Abstractness A, Distance from the Main Sequence
  D = |A + I - 1| (Agile PPP / Clean Architecture chs. 13-14)
- Dependency cycles (Acyclic Dependencies Principle) via Tarjan SCC
- Test presence and test-to-source LOC ratio

Stdlib only, Python 3.10+. Python is parsed with ast (reliable). JS/TS is
parsed with regex heuristics: the import graph is reliable, function-level
numbers are approximate and marked as such in the output.

Usage:
    python3 metrics.py <repo_root> [--out metrics.json] [--max-listed 50]
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
TEST_DIR_NAMES = {'test', 'tests', '__tests__', 'spec', 'specs'}

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


def iter_source_files(root: Path) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for path in sorted(root.rglob('*')):
        language = language_of(path)
        if not path.is_file() or language is None:
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS or part.startswith('.') for part in rel_parts[:-1]):
            continue
        if path.name.endswith(('.min.js', '.bundle.js', '.d.ts')):
            continue
        found.append((path, language))
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
    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
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


def _reference_name(expr: ast.expr) -> str:
    if isinstance(expr, ast.Attribute):
        return expr.attr
    if isinstance(expr, ast.Name):
        return expr.id
    return ''


def _has_abstract_method(node: ast.ClassDef) -> bool:
    methods = [i for i in node.body if isinstance(i, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return any(
        _reference_name(deco) in ('abstractmethod', 'abstractproperty')
        for method in methods
        for deco in method.decorator_list
    )


def class_is_abstract(node: ast.ClassDef) -> bool:
    if any(_reference_name(base) in ('ABC', 'Protocol', 'ABCMeta') for base in node.bases):
        return True
    if any(kw.arg == 'metaclass' for kw in node.keywords):
        return True
    return _has_abstract_method(node)


def resolve_from_import(node: ast.ImportFrom, package_parts: list[str]) -> str:
    if node.level == 0:
        return node.module or ''
    base = package_parts[: len(package_parts) - node.level + 1]
    prefix = '.'.join(base)
    return f'{prefix}.{node.module}' if node.module else prefix


def python_imports(tree: ast.Module, module: str) -> list[str]:
    imports: list[str] = []
    package_parts = module.split('.')[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            resolved = resolve_from_import(node, package_parts)
            if resolved:
                imports.append(resolved)
    return imports


def analyze_python(rel: Path, text: str) -> FileMetric:
    loc, long_lines = count_loc(text)
    metric = FileMetric(str(rel), 'python', loc, long_lines, is_test=is_test_path(rel))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return metric
    module = module_name_for(rel)
    metric.imports = python_imports(tree, module)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            metric.classes += 1
            if class_is_abstract(node):
                metric.abstract_classes += 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params, bool_params = python_param_stats(node)
            end = getattr(node, 'end_lineno', node.lineno)
            metric.functions.append(
                FunctionMetric(
                    str(rel),
                    node.name,
                    node.lineno,
                    end - node.lineno + 1,
                    params,
                    bool_params,
                    python_max_depth(node),
                )
            )
    return metric


def js_function_end(lines: list[str], start: int) -> int:
    depth = 0
    opened = False
    for idx in range(start, len(lines)):
        for char in lines[idx]:
            if char == '{':
                depth += 1
                opened = True
            elif char == '}':
                depth -= 1
        if opened and depth <= 0:
            return idx
        if not opened and lines[idx].rstrip().endswith((';', ',')) and idx > start:
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


def analyze_js(rel: Path, text: str, language: str) -> FileMetric:
    loc, long_lines = count_loc(text)
    metric = FileMetric(str(rel), language, loc, long_lines, is_test=is_test_path(rel))
    metric.imports = JS_IMPORT_RE.findall(text)
    if language == 'typescript':
        metric.classes = len(TS_CLASS_RE.findall(text)) + len(
            re.findall(r'^\s*(?:export\s+)?interface\s+[\w$]+', text, re.MULTILINE)
        )
        metric.abstract_classes = len(TS_ABSTRACT_RE.findall(text))
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        for pattern in JS_FUNC_RES:
            match = pattern.match(line)
            if not match:
                continue
            name = match.group(1) or '<anonymous>'
            raw_params = match.group(2)
            end = js_function_end(lines, idx)
            params, bool_params = js_param_stats(raw_params)
            metric.functions.append(
                FunctionMetric(
                    str(rel),
                    name,
                    idx + 1,
                    end - idx + 1,
                    params,
                    bool_params,
                    -1,
                    approximate=True,
                )
            )
            break
    return metric


def module_name_for(rel: Path) -> str:
    parts = list(rel.parts)
    parts[-1] = rel.stem
    if parts[-1] in ('__init__', 'index'):
        parts = parts[:-1]
    return '.'.join(parts) if parts else rel.stem


def resolve_js_import(spec: str, importer: Path) -> str | None:
    if not spec.startswith('.'):
        return None
    base = importer.parent
    target = (base / spec).resolve()
    try:
        rel = target.relative_to(Path.cwd().resolve())
    except ValueError:
        rel = Path(*target.parts[-len(spec.split('/')) - len(base.parts) :])
    return str(rel)


def package_of(module: str, depth: int = 1, strip: tuple[str, ...] = ('src', 'lib', 'app')) -> str:
    parts = module.split('.')
    while len(parts) > 1 and parts[0] in strip:
        parts = parts[1:]
    return '.'.join(parts[: max(depth, 1)]) if len(parts) > 1 else parts[0]


def build_module_graph(metrics: list[FileMetric]) -> dict[str, set[str]]:
    modules = {module_name_for(Path(m.path)): m for m in metrics}
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for metric in metrics:
        source = module_name_for(Path(metric.path))
        for imp in metric.imports:
            target = resolve_internal(imp, metric, modules)
            if target and target != source:
                graph[source].add(target)
    return graph


def resolve_python_import(imp: str, modules: dict[str, FileMetric]) -> str | None:
    candidate = imp
    while candidate:
        if candidate in modules:
            return candidate
        candidate = candidate.rpartition('.')[0]
    return None


def normalize_parts(parts: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for part in parts:
        if part == '..':
            if normalized:
                normalized.pop()
        elif part not in ('.', ''):
            normalized.append(part)
    return normalized


def resolve_relative_import(
    imp: str, metric: FileMetric, modules: dict[str, FileMetric]
) -> str | None:
    if not imp.startswith('.'):
        return None
    joined = Path(metric.path).parent.joinpath(imp)
    candidate = '.'.join(normalize_parts(joined.parts))
    for suffix in ('', '.index'):
        if candidate + suffix in modules:
            return candidate + suffix
    return None


def resolve_internal(imp: str, metric: FileMetric, modules: dict[str, FileMetric]) -> str | None:
    if metric.language == 'python':
        return resolve_python_import(imp, modules)
    return resolve_relative_import(imp, metric, modules)


@dataclass
class TarjanState:
    graph: dict[str, set[str]]
    stack: list[str] = field(default_factory=list)
    index: dict[str, int] = field(default_factory=dict)
    lowlinks: dict[str, int] = field(default_factory=dict)
    on_stack: set[str] = field(default_factory=set)
    sccs: list[list[str]] = field(default_factory=list)

    def visit(self, node: str) -> tuple[str, Iterator[str]]:
        self.index[node] = self.lowlinks[node] = len(self.index)
        self.stack.append(node)
        self.on_stack.add(node)
        return node, iter(sorted(self.graph.get(node, ())))

    def next_unvisited_child(self, current: str, children: Iterator[str]) -> str | None:
        for child in children:
            if child not in self.index:
                return child
            if child in self.on_stack:
                self.lowlinks[current] = min(self.lowlinks[current], self.index[child])
        return None

    def pop_component(self, root: str) -> None:
        component: list[str] = []
        while True:
            member = self.stack.pop()
            self.on_stack.discard(member)
            component.append(member)
            if member == root:
                break
        self.sccs.append(sorted(component))

    def strongconnect(self, start: str) -> None:
        worklist = [self.visit(start)]
        while worklist:
            current, children = worklist[-1]
            child = self.next_unvisited_child(current, children)
            if child is not None:
                worklist.append(self.visit(child))
                continue
            worklist.pop()
            if worklist:
                parent = worklist[-1][0]
                self.lowlinks[parent] = min(self.lowlinks[parent], self.lowlinks[current])
            if self.lowlinks[current] == self.index[current]:
                self.pop_component(current)


def tarjan_sccs(graph: dict[str, set[str]]) -> list[list[str]]:
    state = TarjanState(graph)
    for node in sorted(graph):
        if node not in state.index:
            state.strongconnect(node)
    return [scc for scc in state.sccs if len(scc) > 1]


def package_edges(graph: dict[str, set[str]], depth: int) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for source, targets in graph.items():
        for target in targets:
            src_pkg, dst_pkg = package_of(source, depth), package_of(target, depth)
            if src_pkg != dst_pkg:
                edges.add((src_pkg, dst_pkg))
    return edges


def package_totals(metrics: list[FileMetric], depth: int) -> dict[str, dict[str, Any]]:
    by_module = {module_name_for(Path(m.path)): m for m in metrics}
    packages: dict[str, dict[str, Any]] = {}
    for module, metric in by_module.items():
        pkg = packages.setdefault(
            package_of(module, depth),
            {'modules': 0, 'classes': 0, 'abstract_classes': 0, 'loc': 0},
        )
        pkg['modules'] += 1
        pkg['classes'] += metric.classes
        pkg['abstract_classes'] += metric.abstract_classes
        pkg['loc'] += metric.loc
    return packages


def add_coupling(name: str, pkg: dict[str, Any], edges: set[tuple[str, str]]) -> None:
    ce = sum(1 for src, dst in edges if src == name)
    ca = sum(1 for src, dst in edges if dst == name)
    instability = round(ce / (ca + ce), 3) if (ca + ce) else None
    abstractness = round(pkg['abstract_classes'] / pkg['classes'], 3) if pkg['classes'] else None
    distance = None
    if instability is not None and abstractness is not None:
        distance = round(abs(abstractness + instability - 1), 3)
    pkg.update(
        {
            'fan_in_ca': ca,
            'fan_out_ce': ce,
            'instability_i': instability,
            'abstractness_a': abstractness,
            'distance_d': distance,
        }
    )


def package_metrics(
    graph: dict[str, set[str]], metrics: list[FileMetric], depth: int = 1
) -> dict[str, Any]:
    edges = package_edges(graph, depth)
    packages = package_totals(metrics, depth)
    for name, pkg in packages.items():
        add_coupling(name, pkg, edges)
    package_graph: dict[str, set[str]] = {}
    for src, dst in edges:
        package_graph.setdefault(src, set()).add(dst)
        package_graph.setdefault(dst, set())
    return {'packages': packages, 'package_cycles': tarjan_sccs(package_graph)}


def collect_violations(metrics: list[FileMetric], cap: int) -> dict[str, Any]:
    functions = [f for m in metrics for f in m.functions]

    def listing(
        items: list[FunctionMetric], key: Callable[[FunctionMetric], int]
    ) -> list[dict[str, Any]]:
        ranked = sorted(items, key=key, reverse=True)[:cap]
        return [
            {
                'file': f.file,
                'name': f.name,
                'line': f.line,
                'loc': f.loc,
                'params': f.params,
                'bool_params': f.bool_params,
                'max_depth': f.max_depth,
                'approximate': f.approximate,
            }
            for f in ranked
        ]

    over_loc = [f for f in functions if f.loc > FUNCTION_LOC_LIMIT]
    over_params = [f for f in functions if f.params > PARAM_LIMIT]
    flag_args = [f for f in functions if f.bool_params > 0]
    deep = [f for f in functions if f.max_depth > DEPTH_LIMIT]
    big_files = sorted(
        (m for m in metrics if m.loc > FILE_LOC_LIMIT), key=lambda m: m.loc, reverse=True
    )
    return {
        'functions_over_20_loc': {
            'count': len(over_loc),
            'worst': listing(over_loc, lambda f: f.loc),
        },
        'functions_over_3_params': {
            'count': len(over_params),
            'worst': listing(over_params, lambda f: f.params),
        },
        'functions_with_bool_params': {
            'count': len(flag_args),
            'worst': listing(flag_args, lambda f: f.bool_params),
        },
        'functions_nested_deeper_than_2': {
            'count': len(deep),
            'worst': listing(deep, lambda f: f.max_depth),
        },
        'files_over_500_loc': [{'file': m.path, 'loc': m.loc} for m in big_files[:cap]],
        'long_lines_over_120_chars': sum(m.long_lines for m in metrics),
    }


def summarize(
    metrics: list[FileMetric], graph: dict[str, set[str]], cap: int, *, depth: int = 1
) -> dict[str, Any]:
    src = [m for m in metrics if not m.is_test]
    tests = [m for m in metrics if m.is_test]
    src_loc = sum(m.loc for m in src)
    test_loc = sum(m.loc for m in tests)
    functions = [f for m in metrics for f in m.functions]
    langs: dict[str, int] = {}
    for metric in metrics:
        langs[metric.language] = langs.get(metric.language, 0) + metric.loc
    module_cycles = tarjan_sccs(graph)
    pkg = package_metrics(graph, metrics, depth)
    return {
        'tool': 'uncle-bob metrics.py',
        'granularity_note': (
            'fan-in/fan-out counted at module level, rolled up to top-level packages'
        ),
        'totals': {
            'files': len(metrics),
            'source_files': len(src),
            'test_files': len(tests),
            'source_loc': src_loc,
            'test_loc': test_loc,
            'test_to_source_ratio': round(test_loc / src_loc, 3) if src_loc else None,
            'functions_measured': len(functions),
            'loc_by_language': langs,
        },
        'component_metrics': pkg,
        'module_cycles_adp': {
            'count': len(module_cycles),
            'cycles': [c[:20] for c in module_cycles[:cap]],
        },
        'violations': collect_violations(metrics, cap),
    }


def render_summary(report: dict[str, Any]) -> str:
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
        f'functions > {FUNCTION_LOC_LIMIT} LOC\t{violations["functions_over_20_loc"]["count"]}',
        f'functions > {PARAM_LIMIT} params\t{violations["functions_over_3_params"]["count"]}',
        f'functions with bool params\t{violations["functions_with_bool_params"]["count"]}',
        (
            f'functions nested > {DEPTH_LIMIT}'
            f'\t{violations["functions_nested_deeper_than_2"]["count"]}'
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


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def analyze_tree(root: Path) -> list[FileMetric]:
    metrics: list[FileMetric] = []
    for path, language in iter_source_files(root):
        text = read_text(path)
        if text is None:
            continue
        rel = path.relative_to(root)
        if language == 'python':
            metrics.append(analyze_python(rel, text))
        else:
            metrics.append(analyze_js(rel, text, language))
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description='Uncle Bob mechanical code metrics')
    parser.add_argument('root', type=Path)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--max-listed', type=int, default=50)
    parser.add_argument(
        '--package-depth',
        type=int,
        default=1,
        help='path components per component rollup; use 2+ for single-package repos',
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f'error: {root} is not a directory', file=sys.stderr)
        return 2
    metrics = analyze_tree(root)
    graph = build_module_graph(metrics)
    report = summarize(metrics, graph, args.max_listed, depth=args.package_depth)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, sort_keys=False))
        print(f'wrote {args.out}')
    print(render_summary(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
