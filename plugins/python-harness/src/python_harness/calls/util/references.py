"""Resolving names and attribute chains to target symbols, and tallying each use."""

import ast
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from itertools import chain, repeat
from types import MappingProxyType

from python_harness.calls.domain import (
    ModuleScope,
    Reference,
    ReferenceContext,
    SymbolDefinition,
    SymbolUsage,
)
from python_harness.core.syntax import annotation_of, dotted_name

type ParentMap = Mapping[ast.AST, ast.AST]
type ReferenceNode = ast.Name | ast.Attribute
type FoundReference = tuple[str, Reference]
type ReferenceIndex = Mapping[str, tuple[Reference, ...]]


def map_parents(tree: ast.Module) -> ParentMap:
    links = (zip(ast.iter_child_nodes(node), repeat(node)) for node in ast.walk(tree))
    return MappingProxyType(dict(chain.from_iterable(links)))


def walk_ancestry(node: ast.AST, parents: ParentMap) -> Iterator[tuple[ast.AST, ast.AST]]:
    child = node
    while (parent := parents.get(child)) is not None:
        yield child, parent
        child = parent


def is_inside_annotation(node: ast.AST, parents: ParentMap) -> bool:
    ancestry = walk_ancestry(node, parents)
    return any(annotation_of(parent) is child for child, parent in ancestry)


def classify_context(node: ReferenceNode, parents: ParentMap) -> ReferenceContext:
    parent = parents.get(node)
    if isinstance(parent, ast.Call) and parent.func is node:
        return ReferenceContext.CALL
    if is_inside_annotation(node, parents):
        return ReferenceContext.ANNOTATION
    return ReferenceContext.NAME


def qualify_node(node: ReferenceNode, local_names: Mapping[str, str]) -> str | None:
    dotted = dotted_name(node)
    if dotted is None:
        return None
    head, separator, tail = dotted.partition('.')
    origin = local_names.get(head)
    if origin is None:
        return None
    return f'{origin}{separator}{tail}'


def select_loaded_references(nodes: Iterable[ast.AST]) -> Iterator[ReferenceNode]:
    candidates = (node for node in nodes if isinstance(node, ast.Name | ast.Attribute))
    return (node for node in candidates if isinstance(node.ctx, ast.Load))


def collect_name_references(scope: ModuleScope, wanted: frozenset[str]) -> Iterator[FoundReference]:
    parents = map_parents(scope.module.tree)
    local_names = scope.local_names
    for node in select_loaded_references(parents):
        qualified = qualify_node(node, local_names)
        if qualified is None or qualified not in wanted:
            continue
        context = classify_context(node, parents)
        yield qualified, Reference(scope.path, node.lineno, context)


def collect_import_references(
    scope: ModuleScope, wanted: frozenset[str]
) -> Iterator[FoundReference]:
    matching = (item for item in scope.bindings if item.bound_name in wanted)
    for item in matching:
        yield item.bound_name, Reference(scope.path, item.line, ReferenceContext.IMPORT)


def collect_references(scope: ModuleScope, wanted: frozenset[str]) -> Iterator[FoundReference]:
    yield from collect_import_references(scope, wanted)
    yield from collect_name_references(scope, wanted)


def collect_scope_references(
    scope: ModuleScope, wanted: frozenset[str]
) -> tuple[FoundReference, ...]:
    try:
        return tuple(collect_references(scope, wanted))
    except RecursionError:
        return ()


def group_references(found: Iterable[FoundReference]) -> ReferenceIndex:
    grouped: defaultdict[str, list[Reference]] = defaultdict(list)
    for qualified, reference in found:
        grouped[qualified].append(reference)
    ordered = {name: tuple(sorted(items)) for name, items in grouped.items()}
    return MappingProxyType(ordered)


def index_references(
    definitions: Iterable[SymbolDefinition], scopes: Iterable[ModuleScope]
) -> ReferenceIndex:
    wanted = frozenset(item.qualified_name() for item in definitions)
    found = chain.from_iterable(collect_scope_references(scope, wanted) for scope in scopes)
    return group_references(found)


def describe_symbol_usage(
    definitions: Iterable[SymbolDefinition], references: ReferenceIndex
) -> tuple[SymbolUsage, ...]:
    return tuple(
        SymbolUsage(item, references.get(item.qualified_name(), ())) for item in definitions
    )
