"""What the `ast` module measures in a Python file, so its numbers are exact."""

import ast
from dataclasses import replace
from typing import TYPE_CHECKING

from mightymodels_cli.review_metrics.files import count_loc, is_test_path, module_name_for
from mightymodels_cli.review_metrics.shapes import FileMetric, FunctionMetric

if TYPE_CHECKING:
    from pathlib import Path


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
    deepest = depth
    for stmt in node.body:
        deepest = max(deepest, dispatch_depth(stmt, depth))
    if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
        return max(deepest, if_chain_depth(node.orelse[0], depth))
    for stmt in node.orelse:
        deepest = max(deepest, dispatch_depth(stmt, depth))
    return deepest


def ast_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ''


def is_abstract_method(item: ast.stmt) -> bool:
    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(
        ast_name(decorator) in ('abstractmethod', 'abstractproperty')
        for decorator in item.decorator_list
    )


def class_is_abstract(node: ast.ClassDef) -> bool:
    if any(ast_name(base) in ('ABC', 'Protocol', 'ABCMeta') for base in node.bases):
        return True
    if any(keyword.arg == 'metaclass' for keyword in node.keywords):
        return True
    return any(map(is_abstract_method, node.body))


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


def analyze_python(rel: Path, text: str) -> FileMetric:
    loc, long_lines = count_loc(text)
    metric = FileMetric(
        path=str(rel),
        language='python',
        loc=loc,
        long_lines=long_lines,
        is_test=is_test_path(rel),
    )
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return metric
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    return replace(
        metric,
        classes=len(classes),
        abstract_classes=sum(1 for node in classes if class_is_abstract(node)),
        functions=tuple(
            python_function(node, rel)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        imports=tuple(python_imports(tree, module_name_for(rel))),
    )


def python_function(node: ast.FunctionDef | ast.AsyncFunctionDef, rel: Path) -> FunctionMetric:
    params, bool_params = python_param_stats(node)
    end = getattr(node, 'end_lineno', node.lineno)
    return FunctionMetric(
        file=str(rel),
        name=node.name,
        line=node.lineno,
        loc=end - node.lineno + 1,
        params=params,
        bool_params=bool_params,
        max_depth=python_max_depth(node),
    )
