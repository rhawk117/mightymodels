"""Try blocks, handlers of the exception base classes, and raises without a cause."""

import ast
from collections.abc import Iterator
from itertools import chain

from python_harness.core.syntax import count_block_statements
from python_harness.facts.domain import (
    AncestorChain,
    ExceptionBaseHandler,
    Fact,
    NodeDetector,
    RaiseWithoutCause,
    TryBlock,
)
from python_harness.facts.util.traversal import ancestors_within_scope, symbol_of

type TryStatement = ast.Try | ast.TryStar

BARE_HANDLER = 'bare'
EXCEPTION_BASE_NAMES = frozenset({'Exception', 'BaseException', BARE_HANDLER})


def caught_names(handler: ast.ExceptHandler) -> tuple[str, ...]:
    caught = handler.type
    if caught is None:
        return (BARE_HANDLER,)
    if isinstance(caught, ast.Tuple):
        return tuple(ast.unparse(item) for item in caught.elts)
    return (ast.unparse(caught),)


def describe_try_block(statement: TryStatement) -> TryBlock:
    caught = chain.from_iterable(caught_names(item) for item in statement.handlers)
    return TryBlock(
        handlers=len(statement.handlers),
        statements_in_try=count_block_statements(statement.body),
        caught=tuple(caught),
    )


def raises_new_exception_without_cause(statement: ast.Raise) -> bool:
    return isinstance(statement.exc, ast.Call) and statement.cause is None


def is_inside_except_handler(ancestors: AncestorChain) -> bool:
    lineage = ancestors_within_scope(ancestors)
    return any(isinstance(node, ast.ExceptHandler) for node in lineage)


def detect_try_block(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, (ast.Try, ast.TryStar)):
        yield Fact(node.lineno, symbol_of(node, ancestors), describe_try_block(node))


def detect_exception_base_handler(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.ExceptHandler):
        names = (name for name in caught_names(node) if name in EXCEPTION_BASE_NAMES)
        symbol = symbol_of(node, ancestors)
        yield from (Fact(node.lineno, symbol, ExceptionBaseHandler(name)) for name in names)


def detect_raise_without_cause(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if not isinstance(node, ast.Raise) or not raises_new_exception_without_cause(node):
        return
    if is_inside_except_handler(ancestors):
        yield Fact(node.lineno, symbol_of(node, ancestors), RaiseWithoutCause())


EXCEPTION_DETECTORS: tuple[NodeDetector, ...] = (
    detect_try_block,
    detect_exception_base_handler,
    detect_raise_without_cause,
)
