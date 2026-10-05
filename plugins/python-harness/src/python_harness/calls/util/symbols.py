"""Top-level symbols per module, each module's name scope, and the targeted scopes."""

import ast
from collections.abc import Iterable, Mapping
from itertools import chain
from types import MappingProxyType

from python_harness.calls.domain import (
    ModuleScope,
    SymbolDefinition,
    SymbolKind,
    TargetedProject,
)
from python_harness.core.sources import ParsedModule, UnparsableSource
from python_harness.core.syntax import DEFINITION_TYPES, FUNCTION_TYPES, dotted_name
from python_harness.imports.domain import ImportGraph, ProjectIndex

TOO_DEEP_MESSAGE = 'nested too deeply to walk'


def is_dunder(name: str) -> bool:
    return name.startswith('__') and name.endswith('__')


def assignment_targets(statement: ast.stmt) -> tuple[ast.expr, ...]:
    if isinstance(statement, ast.Assign):
        return tuple(statement.targets)
    if isinstance(statement, ast.AnnAssign):
        return (statement.target,)
    if isinstance(statement, ast.TypeAlias):
        return (statement.name,)
    return ()


def statement_names(statement: ast.stmt) -> tuple[str, ...]:
    if isinstance(statement, DEFINITION_TYPES):
        return (statement.name,)
    targets = assignment_targets(statement)
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def statement_kind(statement: ast.stmt) -> SymbolKind:
    if isinstance(statement, FUNCTION_TYPES):
        return SymbolKind.FUNCTION
    if isinstance(statement, ast.ClassDef):
        return SymbolKind.CLASS
    return SymbolKind.CONSTANT


def define_statement_symbols(
    statement: ast.stmt, module_name: str, path: str
) -> tuple[SymbolDefinition, ...]:
    kind = statement_kind(statement)
    names = (name for name in statement_names(statement) if not is_dunder(name))
    return tuple(
        SymbolDefinition(module_name, path, name, kind, statement.lineno) for name in names
    )


def top_level_symbols(module: ParsedModule, module_name: str) -> tuple[SymbolDefinition, ...]:
    path = module.source.path
    defined = (
        define_statement_symbols(statement, module_name, path) for statement in module.tree.body
    )
    return tuple(chain.from_iterable(defined))


def build_scope(name: str, module: ParsedModule, graph: ImportGraph) -> ModuleScope:
    return ModuleScope(name, module, graph.bindings_in(name), top_level_symbols(module, name))


def scope_project(project: Iterable[ParsedModule], graph: ImportGraph) -> Mapping[str, ModuleScope]:
    by_path = {module.source.path: module for module in project}
    refs = (ref for ref in graph.modules.values() if ref.path in by_path)
    scopes = (build_scope(ref.name, by_path[ref.path], graph) for ref in refs)
    return MappingProxyType({scope.name: scope for scope in scopes})


def can_walk_references(module: ParsedModule) -> bool:
    attributes = (node for node in ast.walk(module.tree) if isinstance(node, ast.Attribute))
    try:
        tuple(map(dotted_name, attributes))
    except RecursionError:
        return False
    return True


def select_targets(index: ProjectIndex, target_paths: frozenset[str]) -> TargetedProject:
    modules = index.sources.modules
    walkable = tuple(module for module in modules if can_walk_references(module))
    too_deep = tuple(module for module in modules if module not in walkable)
    scopes = scope_project(walkable, index.graph)
    targeted = (scopes[name] for name in sorted(scopes))
    targets = tuple(scope for scope in targeted if scope.path in target_paths)
    reported = (
        *index.sources.unparsable,
        *(UnparsableSource(module.source.path, None, TOO_DEEP_MESSAGE) for module in too_deep),
    )
    unparsable = tuple(item for item in reported if item.path in target_paths)
    return TargetedProject(index.graph, scopes, targets, unparsable)
