"""One ancestor-aware walk over a tree, and the symbol each visited node belongs to."""

import ast
from collections.abc import Iterator
from typing import TYPE_CHECKING

from python_harness.core.syntax import DEFINITION_TYPES, SCOPE_TYPES
from python_harness.facts.domain import AncestorChain, Fact, NodeDetector

if TYPE_CHECKING:
    from python_harness.core.syntax import FunctionDefinition

type VisitedNode = tuple[ast.AST, AncestorChain]
type Definition = ast.ClassDef | FunctionDefinition


def walk_with_ancestors(node: ast.AST, ancestors: AncestorChain = ()) -> Iterator[VisitedNode]:
    yield node, ancestors
    lineage = (*ancestors, node)
    for child in ast.iter_child_nodes(node):
        yield from walk_with_ancestors(child, lineage)


def run_detectors(tree: ast.AST, detectors: tuple[NodeDetector, ...]) -> Iterator[Fact]:
    for node, ancestors in walk_with_ancestors(tree):
        for detect in detectors:
            yield from detect(node, ancestors)


def enclosing_symbol(ancestors: AncestorChain) -> str | None:
    names = [node.name for node in ancestors if isinstance(node, DEFINITION_TYPES)]
    return '.'.join(names) or None


def qualified_name(definition: Definition, ancestors: AncestorChain) -> str:
    outer = enclosing_symbol(ancestors)
    return definition.name if outer is None else f'{outer}.{definition.name}'


def symbol_of(node: ast.AST, ancestors: AncestorChain) -> str | None:
    if isinstance(node, DEFINITION_TYPES):
        return qualified_name(node, ancestors)
    return enclosing_symbol(ancestors)


def enclosing_class(ancestors: AncestorChain) -> ast.ClassDef | None:
    parent = ancestors[-1] if ancestors else None
    return parent if isinstance(parent, ast.ClassDef) else None


def ancestors_within_scope(ancestors: AncestorChain) -> AncestorChain:
    boundaries = (index for index, node in enumerate(ancestors) if isinstance(node, SCOPE_TYPES))
    innermost = max(boundaries, default=-1)
    return ancestors[innermost + 1 :]
