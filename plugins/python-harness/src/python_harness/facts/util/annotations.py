"""Annotation shapes: inline Annotated, postponed evaluation, Any and TypeAlias."""

import ast
from collections.abc import Iterator

from python_harness.core.syntax import annotation_of, terminal_name
from python_harness.facts.domain import (
    AncestorChain,
    AnyAnnotation,
    Fact,
    FutureAnnotations,
    InlineAnnotated,
    NodeDetector,
    TypeAliasAnnotation,
)
from python_harness.facts.util.traversal import enclosing_class, symbol_of

type NameReference = ast.Name | ast.Attribute


def signature_or_field_annotation_of(node: ast.AST, ancestors: AncestorChain) -> ast.expr | None:
    if isinstance(node, ast.AnnAssign) and enclosing_class(ancestors) is None:
        return None
    return annotation_of(node)


def references_to(name: str, annotation: ast.expr | None) -> Iterator[NameReference]:
    nodes = () if annotation is None else ast.walk(annotation)
    references = (item for item in nodes if isinstance(item, (ast.Name, ast.Attribute)))
    return (item for item in references if terminal_name(item) == name)


def imports_future_annotations(statement: ast.ImportFrom) -> bool:
    names = (alias.name for alias in statement.names)
    return statement.module == '__future__' and 'annotations' in names


def detect_inline_annotated(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    annotation = signature_or_field_annotation_of(node, ancestors)
    yield from (
        Fact(item.lineno, symbol_of(node, ancestors), InlineAnnotated())
        for item in references_to('Annotated', annotation)
    )


def detect_future_annotations(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.ImportFrom) and imports_future_annotations(node):
        yield Fact(node.lineno, symbol_of(node, ancestors), FutureAnnotations())


def detect_any_annotation(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    yield from (
        Fact(item.lineno, symbol_of(node, ancestors), AnyAnnotation())
        for item in references_to('Any', annotation_of(node))
    )


def detect_typealias_annotation(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.AnnAssign) and terminal_name(node.annotation) == 'TypeAlias':
        yield Fact(node.lineno, symbol_of(node, ancestors), TypeAliasAnnotation())


ANNOTATION_DETECTORS: tuple[NodeDetector, ...] = (
    detect_inline_annotated,
    detect_future_annotations,
    detect_any_annotation,
    detect_typealias_annotation,
)
