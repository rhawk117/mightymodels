"""Module-level and process state: globals, import-time calls, sys.path, os.environ."""

import ast
from collections.abc import Iterator
from itertools import pairwise

from python_harness.core.syntax import SCOPE_TYPES, dotted_name
from python_harness.facts.domain import (
    AncestorChain,
    Fact,
    GlobalStatement,
    LambdaInCollection,
    ModuleLevelCall,
    MutableModuleGlobal,
    NodeDetector,
    OsEnviron,
    SysPathMutation,
)
from python_harness.facts.util.shapes import is_in_body, is_mutable_value
from python_harness.facts.util.traversal import symbol_of

MUTABLE_GLOBAL_CONSTRUCTORS = frozenset(
    {
        'dict',
        'list',
        'set',
        'defaultdict',
        'OrderedDict',
        'deque',
        'collections.defaultdict',
        'collections.OrderedDict',
        'collections.deque',
    }
)
SYS_PATH_METHODS = frozenset({'append', 'extend', 'insert', 'remove', 'pop', 'clear'})
COLLECTION_DISPLAY_TYPES = (ast.Dict, ast.List, ast.Set, ast.Tuple)
ASSIGNMENT_TYPES = (ast.Assign, ast.AnnAssign)

type Assignment = ast.Assign | ast.AnnAssign


def is_module_level(ancestors: AncestorChain) -> bool:
    return not any(isinstance(node, SCOPE_TYPES) for node in ancestors)


def bound_names(statement: Assignment) -> tuple[str, ...]:
    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def assigns_mutable_value(statement: Assignment) -> bool:
    value = statement.value
    return value is not None and is_mutable_value(value, MUTABLE_GLOBAL_CONSTRUCTORS)


def is_main_guard(statement: ast.If) -> bool:
    test = statement.test
    if not isinstance(test, ast.Compare) or not isinstance(test.ops[0], ast.Eq):
        return False
    operands = (test.left, *test.comparators)
    names = {item.id for item in operands if isinstance(item, ast.Name)}
    texts = {item.value for item in operands if isinstance(item, ast.Constant)}
    return names == {'__name__'} and texts == {'__main__'}


def is_under_main_guard(node: ast.AST, ancestors: AncestorChain) -> bool:
    lineage = pairwise((*ancestors, node))
    return any(
        isinstance(parent, ast.If) and is_main_guard(parent) and is_in_body(child, parent)
        for parent, child in lineage
    )


def expression_call(node: ast.AST) -> ast.Call | None:
    value = node.value if isinstance(node, ast.Expr) else None
    return value if isinstance(value, ast.Call) else None


def rebound_targets(node: ast.AST) -> list[ast.expr]:
    if isinstance(node, (ast.Assign, ast.Delete)):
        return node.targets
    if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        return [node.target]
    return []


def is_sys_path_reference(expression: ast.expr) -> bool:
    target = expression.value if isinstance(expression, ast.Subscript) else expression
    return dotted_name(target) == 'sys.path'


def is_sys_path_method(callee: ast.expr) -> bool:
    if not isinstance(callee, ast.Attribute) or callee.attr not in SYS_PATH_METHODS:
        return False
    return dotted_name(callee.value) == 'sys.path'


def detect_mutable_module_global(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if not isinstance(node, ASSIGNMENT_TYPES) or not assigns_mutable_value(node):
        return
    if is_module_level(ancestors):
        symbol = symbol_of(node, ancestors)
        yield from (
            Fact(node.lineno, symbol, MutableModuleGlobal(name)) for name in bound_names(node)
        )


def detect_global_statement(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.Global):
        yield Fact(node.lineno, symbol_of(node, ancestors), GlobalStatement())


def detect_module_level_call(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    call = expression_call(node)
    if call is None or not is_module_level(ancestors):
        return
    if not is_under_main_guard(node, ancestors):
        detail = ModuleLevelCall(call=ast.unparse(call.func))
        yield Fact(call.lineno, symbol_of(node, ancestors), detail)


def detect_sys_path_rebinding(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    targets = rebound_targets(node)
    if isinstance(node, ast.stmt) and any(map(is_sys_path_reference, targets)):
        yield Fact(node.lineno, symbol_of(node, ancestors), SysPathMutation())


def detect_sys_path_method_call(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.Call) and is_sys_path_method(node.func):
        yield Fact(node.lineno, symbol_of(node, ancestors), SysPathMutation())


def detect_os_environ(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.Attribute) and dotted_name(node) == 'os.environ':
        yield Fact(node.lineno, symbol_of(node, ancestors), OsEnviron())


def detect_lambda_in_collection(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    parent = ancestors[-1] if ancestors else None
    if isinstance(node, ast.Lambda) and isinstance(parent, COLLECTION_DISPLAY_TYPES):
        yield Fact(node.lineno, symbol_of(node, ancestors), LambdaInCollection())


MODULE_STATE_DETECTORS: tuple[NodeDetector, ...] = (
    detect_mutable_module_global,
    detect_global_statement,
    detect_module_level_call,
    detect_sys_path_rebinding,
    detect_sys_path_method_call,
    detect_os_environ,
    detect_lambda_in_collection,
)
