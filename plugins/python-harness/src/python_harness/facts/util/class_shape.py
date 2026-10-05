"""Class shapes: decorators, bases, special methods and class-level annotations."""

import ast
from collections.abc import Iterator
from itertools import product

from python_harness.core.syntax import (
    FUNCTION_TYPES,
    FunctionDefinition,
    count_statements,
    descendants_in_scope,
    find_decorator,
    terminal_name,
)
from python_harness.facts.domain import (
    AbcBase,
    AncestorChain,
    ClassMethod,
    ClassVarAnnotation,
    ConstantFlag,
    DataclassDecorator,
    DataclassFlag,
    ExpressionFlag,
    Fact,
    HandwrittenInit,
    NodeDetector,
    OperatorOverload,
    PostInit,
    PrivateClass,
    ProtocolClass,
    RuntimeCheckable,
    StaticMethod,
)
from python_harness.facts.util.traversal import enclosing_class, symbol_of

EXCEPTION_NAME_SUFFIXES = ('Error', 'Exception')
BINARY_OPERATOR_NAMES = (
    'add',
    'sub',
    'mul',
    'matmul',
    'truediv',
    'floordiv',
    'mod',
    'pow',
    'lshift',
    'rshift',
    'and',
    'xor',
    'or',
)
ARITHMETIC_DUNDERS = frozenset(
    {
        *(f'__{prefix}{name}__' for prefix, name in product(('', 'r', 'i'), BINARY_OPERATOR_NAMES)),
        '__divmod__',
        '__rdivmod__',
        '__neg__',
        '__pos__',
        '__abs__',
        '__invert__',
    }
)
COMPARISON_DUNDERS = frozenset({'__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__'})
CONTAINER_DUNDERS = frozenset(
    {
        '__len__',
        '__getitem__',
        '__setitem__',
        '__delitem__',
        '__contains__',
        '__iter__',
        '__reversed__',
        '__missing__',
    }
)
OPERATOR_DUNDERS = ARITHMETIC_DUNDERS | COMPARISON_DUNDERS | CONTAINER_DUNDERS | {'__call__'}


def subscript_base(expression: ast.expr) -> ast.expr:
    return expression.value if isinstance(expression, ast.Subscript) else expression


def base_names(class_def: ast.ClassDef) -> tuple[str, ...]:
    names = (terminal_name(subscript_base(base)) for base in class_def.bases)
    return tuple(name for name in names if name is not None)


def metaclass_name(class_def: ast.ClassDef) -> str | None:
    keywords = (item for item in class_def.keywords if item.arg == 'metaclass')
    metaclass = next(keywords, None)
    return None if metaclass is None else terminal_name(metaclass.value)


def is_exception_class(class_def: ast.ClassDef) -> bool:
    return any(name.endswith(EXCEPTION_NAME_SUFFIXES) for name in base_names(class_def))


def inherits_abc(class_def: ast.ClassDef) -> bool:
    return 'ABC' in base_names(class_def) or metaclass_name(class_def) == 'ABCMeta'


def is_classvar_annotation(annotation: ast.expr) -> bool:
    return terminal_name(subscript_base(annotation)) == 'ClassVar'


def first_positional_name(function: FunctionDefinition) -> str | None:
    positional = (*function.args.posonlyargs, *function.args.args)
    return positional[0].arg if positional else None


def returned_values(function: FunctionDefinition) -> Iterator[ast.expr]:
    returns = (item for item in descendants_in_scope(function) if isinstance(item, ast.Return))
    return (item.value for item in returns if item.value is not None)


def is_call_to_name(expression: ast.expr, name: str | None) -> bool:
    callee = expression.func if isinstance(expression, ast.Call) else None
    return isinstance(callee, ast.Name) and callee.id == name


def returns_receiver_call(method: FunctionDefinition) -> bool:
    receiver = first_positional_name(method)
    return any(is_call_to_name(value, receiver) for value in returned_values(method))


def dataclass_flag(decorator: ast.expr, flag: str) -> DataclassFlag:
    keywords = decorator.keywords if isinstance(decorator, ast.Call) else []
    value = next((item.value for item in keywords if item.arg == flag), None)
    if value is None:
        return ConstantFlag(value=False)
    if isinstance(value, ast.Constant) and isinstance(value.value, bool):
        return ConstantFlag(value=value.value)
    return ExpressionFlag(source=ast.unparse(value))


def describe_dataclass_decorator(decorator: ast.expr) -> DataclassDecorator:
    return DataclassDecorator(
        frozen=dataclass_flag(decorator, 'frozen'),
        slots=dataclass_flag(decorator, 'slots'),
        kw_only=dataclass_flag(decorator, 'kw_only'),
    )


def detect_staticmethod(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    decorator = find_decorator(node, 'staticmethod')
    if decorator is not None:
        yield Fact(decorator.lineno, symbol_of(node, ancestors), StaticMethod())


def detect_classmethod(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    decorator = find_decorator(node, 'classmethod')
    if decorator is not None and isinstance(node, FUNCTION_TYPES):
        detail = ClassMethod(returns_cls_call=returns_receiver_call(node))
        yield Fact(decorator.lineno, symbol_of(node, ancestors), detail)


def detect_private_class(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.ClassDef) and node.name.startswith('_'):
        yield Fact(node.lineno, symbol_of(node, ancestors), PrivateClass())


def detect_dataclass(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    decorator = find_decorator(node, 'dataclass')
    if decorator is not None:
        detail = describe_dataclass_decorator(decorator)
        yield Fact(decorator.lineno, symbol_of(node, ancestors), detail)


def detect_protocol(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.ClassDef) and 'Protocol' in base_names(node):
        yield Fact(node.lineno, symbol_of(node, ancestors), ProtocolClass())


def detect_runtime_checkable(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    decorator = find_decorator(node, 'runtime_checkable')
    if decorator is not None:
        yield Fact(decorator.lineno, symbol_of(node, ancestors), RuntimeCheckable())


def detect_abc_base(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.ClassDef) and inherits_abc(node):
        yield Fact(node.lineno, symbol_of(node, ancestors), AbcBase())


def detect_handwritten_init(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    owner = enclosing_class(ancestors)
    if owner is None or not isinstance(node, FUNCTION_TYPES) or node.name != '__init__':
        return
    detail = HandwrittenInit(
        statements=count_statements(node), exception_class=is_exception_class(owner)
    )
    yield Fact(node.lineno, symbol_of(node, ancestors), detail)


def detect_post_init(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    owner = enclosing_class(ancestors)
    if owner is None or not isinstance(node, FUNCTION_TYPES):
        return
    if node.name == '__post_init__':
        detail = PostInit(statements=count_statements(node))
        yield Fact(node.lineno, symbol_of(node, ancestors), detail)


def detect_classvar(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    owner = enclosing_class(ancestors)
    if owner is None or not isinstance(node, ast.AnnAssign):
        return
    if is_classvar_annotation(node.annotation):
        in_dataclass = find_decorator(owner, 'dataclass') is not None
        detail = ClassVarAnnotation(in_dataclass=in_dataclass)
        yield Fact(node.lineno, symbol_of(node, ancestors), detail)


def detect_operator_overload(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    owner = enclosing_class(ancestors)
    if owner is None or not isinstance(node, FUNCTION_TYPES):
        return
    if node.name in OPERATOR_DUNDERS:
        detail = OperatorOverload(operator=node.name)
        yield Fact(node.lineno, symbol_of(node, ancestors), detail)


CLASS_SHAPE_DETECTORS: tuple[NodeDetector, ...] = (
    detect_staticmethod,
    detect_classmethod,
    detect_private_class,
    detect_dataclass,
    detect_protocol,
    detect_runtime_checkable,
    detect_abc_base,
    detect_handwritten_init,
    detect_post_init,
    detect_classvar,
    detect_operator_overload,
)
