"""Coupling and size facts for one target module."""

import ast
from typing import TYPE_CHECKING

from python_harness.calls.domain import ModuleMetrics, ModuleScope
from python_harness.calls.util.references import map_parents
from python_harness.core.syntax import (
    FUNCTION_TYPES,
    count_parameters,
    count_statements,
)
from python_harness.imports.domain import ImportGraph

if TYPE_CHECKING:
    from python_harness.core.syntax import FunctionDefinition

type PlacedFunction = tuple[FunctionDefinition, ast.AST]


def find_functions(tree: ast.Module) -> tuple[PlacedFunction, ...]:
    placed = map_parents(tree).items()
    return tuple((node, parent) for node, parent in placed if isinstance(node, FUNCTION_TYPES))


def find_test_importers(graph: ImportGraph, module: str) -> tuple[str, ...]:
    importers = (graph.modules[name] for name in graph.dependents_of(module))
    return tuple(sorted(ref.path for ref in importers if ref.is_test))


def measure_module(scope: ModuleScope, graph: ImportGraph) -> ModuleMetrics:
    functions = find_functions(scope.module.tree)
    statements = (count_statements(function) for function, _ in functions)
    parameters = (count_parameters(function, parent).parameters for function, parent in functions)
    public = sum(1 for item in scope.symbols if item.is_public)
    return ModuleMetrics(
        path=scope.path,
        module=scope.name,
        fan_in=len(graph.dependents_of(scope.name)),
        fan_out=len(graph.dependencies_of(scope.name)),
        public_symbols=public,
        private_symbols=len(scope.symbols) - public,
        function_count=len(functions),
        max_function_statements=max(statements, default=0),
        max_parameters=max(parameters, default=0),
        test_paths=find_test_importers(graph, scope.name),
    )
