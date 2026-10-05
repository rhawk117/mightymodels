"""Function shapes: parameters, statements, block nesting depth and mutable defaults."""

import ast
from collections.abc import Iterator

from python_harness.core.syntax import (
    FUNCTION_TYPES,
    SCOPE_TYPES,
    FunctionDefinition,
    count_parameters,
    count_statements,
)
from python_harness.facts.domain import (
    AncestorChain,
    Fact,
    FunctionShape,
    MutableDefault,
    NodeDetector,
)
from python_harness.facts.util.shapes import elif_branch, is_mutable_value
from python_harness.facts.util.traversal import enclosing_class, symbol_of

BLOCK_TYPES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.Match,
)
MUTABLE_DEFAULT_CONSTRUCTORS = frozenset({'list', 'dict', 'set'})


def opens_nested_block(parent: ast.AST, child: ast.AST) -> bool:
    if not isinstance(child, BLOCK_TYPES):
        return False
    return not isinstance(parent, ast.If) or elif_branch(parent) is not child


def block_depth(node: ast.AST) -> int:
    children = (child for child in ast.iter_child_nodes(node) if not isinstance(child, SCOPE_TYPES))
    depths = (block_depth(child) + int(opens_nested_block(node, child)) for child in children)
    return max(depths, default=0)


def describe_function_shape(
    function: FunctionDefinition, ancestors: AncestorChain
) -> FunctionShape:
    counts = count_parameters(function, enclosing_class(ancestors))
    return FunctionShape(
        parameters=counts.parameters,
        positional=counts.positional,
        statements=count_statements(function),
        max_depth=block_depth(function),
        is_async=isinstance(function, ast.AsyncFunctionDef),
        returns_annotated=function.returns is not None,
    )


def default_values(function: FunctionDefinition) -> tuple[ast.expr, ...]:
    keyword_defaults = (item for item in function.args.kw_defaults if item is not None)
    return (*function.args.defaults, *keyword_defaults)


def detect_function_shape(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, FUNCTION_TYPES):
        shape = describe_function_shape(node, ancestors)
        yield Fact(node.lineno, symbol_of(node, ancestors), shape)


def detect_mutable_default(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, FUNCTION_TYPES):
        defaults = default_values(node)
        mutable = (
            item for item in defaults if is_mutable_value(item, MUTABLE_DEFAULT_CONSTRUCTORS)
        )
        yield from (
            Fact(item.lineno, symbol_of(node, ancestors), MutableDefault()) for item in mutable
        )


FUNCTION_SHAPE_DETECTORS: tuple[NodeDetector, ...] = (
    detect_function_shape,
    detect_mutable_default,
)
