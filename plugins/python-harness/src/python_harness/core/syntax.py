"""Shared AST vocabulary: definitions, dotted names, annotation slots and size counts."""

import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

type FunctionDefinition = ast.FunctionDef | ast.AsyncFunctionDef

FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
DEFINITION_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
SCOPE_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


@dataclass(frozen=True, slots=True)
class ParameterCounts:
    parameters: int
    positional: int


def dotted_name(expression: ast.AST) -> str | None:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        owner = dotted_name(expression.value)
        return None if owner is None else f'{owner}.{expression.attr}'
    return None


def terminal_name(expression: ast.AST) -> str | None:
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        return expression.attr
    return None


def decorator_target(decorator: ast.expr) -> ast.expr:
    return decorator.func if isinstance(decorator, ast.Call) else decorator


def find_decorator(node: ast.AST, name: str) -> ast.expr | None:
    decorators = node.decorator_list if isinstance(node, DEFINITION_TYPES) else []
    matching = (item for item in decorators if terminal_name(decorator_target(item)) == name)
    return next(matching, None)


def annotation_of(node: ast.AST) -> ast.expr | None:
    if isinstance(node, (ast.arg, ast.AnnAssign)):
        return node.annotation
    if isinstance(node, FUNCTION_TYPES):
        return node.returns
    return None


def descendants_in_scope(node: ast.AST) -> Iterator[ast.AST]:
    children = (child for child in ast.iter_child_nodes(node) if not isinstance(child, SCOPE_TYPES))
    for child in children:
        yield child
        yield from descendants_in_scope(child)


def count_nested_statements(node: ast.AST) -> int:
    return sum(isinstance(item, ast.stmt) for item in descendants_in_scope(node))


def count_block_statements(statements: Iterable[ast.stmt]) -> int:
    counted = (item for item in statements if not isinstance(item, SCOPE_TYPES))
    return sum(1 + count_nested_statements(statement) for statement in counted)


def count_statements(function: FunctionDefinition) -> int:
    return count_block_statements(function.body)


def takes_receiver(function: FunctionDefinition, parent: ast.AST | None) -> bool:
    in_class_body = isinstance(parent, ast.ClassDef)
    return in_class_body and find_decorator(function, 'staticmethod') is None


def count_positional(function: FunctionDefinition, parent: ast.AST | None) -> int:
    declared = len(function.args.posonlyargs) + len(function.args.args)
    if declared and takes_receiver(function, parent):
        return declared - 1
    return declared


def count_parameters(function: FunctionDefinition, parent: ast.AST | None) -> ParameterCounts:
    arguments = function.args
    positional = count_positional(function, parent)
    variadic = sum(item is not None for item in (arguments.vararg, arguments.kwarg))
    keyword_only = len(arguments.kwonlyargs)
    return ParameterCounts(positional + keyword_only + variadic, positional)
