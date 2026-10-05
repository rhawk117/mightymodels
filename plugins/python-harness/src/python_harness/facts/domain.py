"""Neutral facts observed in parsed modules, each carrying a detail typed by its kind."""

import ast
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum, auto
from types import MappingProxyType
from typing import Literal, Protocol

from python_harness.core.sources import ParsedModule, UnparsableSource

type AncestorChain = tuple[ast.AST, ...]


class FactKind(StrEnum):
    ELSE_BRANCH = auto()
    WHILE_TRUE = auto()
    BREAK_IN_LOOP = auto()
    RETURN_IN_LOOP = auto()
    MATCH_STATEMENT = auto()
    DEL_STATEMENT = auto()
    TRY_BLOCK = auto()
    EXCEPTION_BASE_HANDLER = auto()
    RAISE_WITHOUT_CAUSE = auto()
    STATICMETHOD = auto()
    CLASSMETHOD = auto()
    PRIVATE_CLASS = auto()
    DATACLASS = auto()
    PROTOCOL = auto()
    RUNTIME_CHECKABLE = auto()
    ABC_BASE = auto()
    HANDWRITTEN_INIT = auto()
    POST_INIT = auto()
    CLASSVAR = auto()
    OPERATOR_OVERLOAD = auto()
    FUNCTION_SHAPE = auto()
    MUTABLE_DEFAULT = auto()
    MUTABLE_MODULE_GLOBAL = auto()
    GLOBAL_STATEMENT = auto()
    MODULE_LEVEL_CALL = auto()
    SYS_PATH_MUTATION = auto()
    OS_ENVIRON = auto()
    LAMBDA_IN_COLLECTION = auto()
    INLINE_ANNOTATED = auto()
    FUTURE_ANNOTATIONS = auto()
    ANY_ANNOTATION = auto()
    TYPEALIAS_ANNOTATION = auto()
    COMMENT = auto()
    DOCSTRING = auto()
    ASYNCIO_GATHER = auto()
    ASYNCIO_TO_THREAD = auto()


@dataclass(frozen=True, slots=True)
class ElseBranch:
    statement: str
    kind: Literal[FactKind.ELSE_BRANCH] = field(default=FactKind.ELSE_BRANCH, init=False)


@dataclass(frozen=True, slots=True)
class WhileTrue:
    kind: Literal[FactKind.WHILE_TRUE] = field(default=FactKind.WHILE_TRUE, init=False)


@dataclass(frozen=True, slots=True)
class BreakInLoop:
    kind: Literal[FactKind.BREAK_IN_LOOP] = field(default=FactKind.BREAK_IN_LOOP, init=False)


@dataclass(frozen=True, slots=True)
class ReturnInLoop:
    kind: Literal[FactKind.RETURN_IN_LOOP] = field(default=FactKind.RETURN_IN_LOOP, init=False)


@dataclass(frozen=True, slots=True)
class MatchStatement:
    kind: Literal[FactKind.MATCH_STATEMENT] = field(default=FactKind.MATCH_STATEMENT, init=False)


@dataclass(frozen=True, slots=True)
class DelStatement:
    kind: Literal[FactKind.DEL_STATEMENT] = field(default=FactKind.DEL_STATEMENT, init=False)


@dataclass(frozen=True, slots=True)
class TryBlock:
    handlers: int
    statements_in_try: int
    caught: tuple[str, ...]
    kind: Literal[FactKind.TRY_BLOCK] = field(default=FactKind.TRY_BLOCK, init=False)


@dataclass(frozen=True, slots=True)
class ExceptionBaseHandler:
    caught: str
    kind: Literal[FactKind.EXCEPTION_BASE_HANDLER] = field(
        default=FactKind.EXCEPTION_BASE_HANDLER, init=False
    )


@dataclass(frozen=True, slots=True)
class RaiseWithoutCause:
    kind: Literal[FactKind.RAISE_WITHOUT_CAUSE] = field(
        default=FactKind.RAISE_WITHOUT_CAUSE, init=False
    )


@dataclass(frozen=True, slots=True)
class StaticMethod:
    kind: Literal[FactKind.STATICMETHOD] = field(default=FactKind.STATICMETHOD, init=False)


@dataclass(frozen=True, slots=True)
class ClassMethod:
    returns_cls_call: bool
    kind: Literal[FactKind.CLASSMETHOD] = field(default=FactKind.CLASSMETHOD, init=False)


@dataclass(frozen=True, slots=True)
class PrivateClass:
    kind: Literal[FactKind.PRIVATE_CLASS] = field(default=FactKind.PRIVATE_CLASS, init=False)


@dataclass(frozen=True, slots=True)
class ConstantFlag:
    value: bool
    kind: Literal['constant'] = field(default='constant', init=False)


@dataclass(frozen=True, slots=True)
class ExpressionFlag:
    source: str
    kind: Literal['expression'] = field(default='expression', init=False)


type DataclassFlag = ConstantFlag | ExpressionFlag


@dataclass(frozen=True, slots=True)
class DataclassDecorator:
    frozen: DataclassFlag
    slots: DataclassFlag
    kw_only: DataclassFlag
    kind: Literal[FactKind.DATACLASS] = field(default=FactKind.DATACLASS, init=False)


@dataclass(frozen=True, slots=True)
class ProtocolClass:
    kind: Literal[FactKind.PROTOCOL] = field(default=FactKind.PROTOCOL, init=False)


@dataclass(frozen=True, slots=True)
class RuntimeCheckable:
    kind: Literal[FactKind.RUNTIME_CHECKABLE] = field(
        default=FactKind.RUNTIME_CHECKABLE, init=False
    )


@dataclass(frozen=True, slots=True)
class AbcBase:
    kind: Literal[FactKind.ABC_BASE] = field(default=FactKind.ABC_BASE, init=False)


@dataclass(frozen=True, slots=True)
class HandwrittenInit:
    statements: int
    exception_class: bool
    kind: Literal[FactKind.HANDWRITTEN_INIT] = field(default=FactKind.HANDWRITTEN_INIT, init=False)


@dataclass(frozen=True, slots=True)
class PostInit:
    statements: int
    kind: Literal[FactKind.POST_INIT] = field(default=FactKind.POST_INIT, init=False)


@dataclass(frozen=True, slots=True)
class ClassVarAnnotation:
    in_dataclass: bool
    kind: Literal[FactKind.CLASSVAR] = field(default=FactKind.CLASSVAR, init=False)


@dataclass(frozen=True, slots=True)
class OperatorOverload:
    operator: str
    kind: Literal[FactKind.OPERATOR_OVERLOAD] = field(
        default=FactKind.OPERATOR_OVERLOAD, init=False
    )


@dataclass(frozen=True, slots=True)
class FunctionShape:
    parameters: int
    positional: int
    statements: int
    max_depth: int
    is_async: bool
    returns_annotated: bool
    kind: Literal[FactKind.FUNCTION_SHAPE] = field(default=FactKind.FUNCTION_SHAPE, init=False)


@dataclass(frozen=True, slots=True)
class MutableDefault:
    kind: Literal[FactKind.MUTABLE_DEFAULT] = field(default=FactKind.MUTABLE_DEFAULT, init=False)


@dataclass(frozen=True, slots=True)
class MutableModuleGlobal:
    name: str
    kind: Literal[FactKind.MUTABLE_MODULE_GLOBAL] = field(
        default=FactKind.MUTABLE_MODULE_GLOBAL, init=False
    )


@dataclass(frozen=True, slots=True)
class GlobalStatement:
    kind: Literal[FactKind.GLOBAL_STATEMENT] = field(default=FactKind.GLOBAL_STATEMENT, init=False)


@dataclass(frozen=True, slots=True)
class ModuleLevelCall:
    call: str
    kind: Literal[FactKind.MODULE_LEVEL_CALL] = field(
        default=FactKind.MODULE_LEVEL_CALL, init=False
    )


@dataclass(frozen=True, slots=True)
class SysPathMutation:
    kind: Literal[FactKind.SYS_PATH_MUTATION] = field(
        default=FactKind.SYS_PATH_MUTATION, init=False
    )


@dataclass(frozen=True, slots=True)
class OsEnviron:
    kind: Literal[FactKind.OS_ENVIRON] = field(default=FactKind.OS_ENVIRON, init=False)


@dataclass(frozen=True, slots=True)
class LambdaInCollection:
    kind: Literal[FactKind.LAMBDA_IN_COLLECTION] = field(
        default=FactKind.LAMBDA_IN_COLLECTION, init=False
    )


@dataclass(frozen=True, slots=True)
class InlineAnnotated:
    kind: Literal[FactKind.INLINE_ANNOTATED] = field(default=FactKind.INLINE_ANNOTATED, init=False)


@dataclass(frozen=True, slots=True)
class FutureAnnotations:
    kind: Literal[FactKind.FUTURE_ANNOTATIONS] = field(
        default=FactKind.FUTURE_ANNOTATIONS, init=False
    )


@dataclass(frozen=True, slots=True)
class AnyAnnotation:
    kind: Literal[FactKind.ANY_ANNOTATION] = field(default=FactKind.ANY_ANNOTATION, init=False)


@dataclass(frozen=True, slots=True)
class TypeAliasAnnotation:
    kind: Literal[FactKind.TYPEALIAS_ANNOTATION] = field(
        default=FactKind.TYPEALIAS_ANNOTATION, init=False
    )


@dataclass(frozen=True, slots=True)
class Comment:
    text: str
    kind: Literal[FactKind.COMMENT] = field(default=FactKind.COMMENT, init=False)


@dataclass(frozen=True, slots=True)
class Docstring:
    owner: str
    kind: Literal[FactKind.DOCSTRING] = field(default=FactKind.DOCSTRING, init=False)


@dataclass(frozen=True, slots=True)
class AsyncioGather:
    kind: Literal[FactKind.ASYNCIO_GATHER] = field(default=FactKind.ASYNCIO_GATHER, init=False)


@dataclass(frozen=True, slots=True)
class AsyncioToThread:
    kind: Literal[FactKind.ASYNCIO_TO_THREAD] = field(
        default=FactKind.ASYNCIO_TO_THREAD, init=False
    )


type FactDetail = (
    ElseBranch
    | WhileTrue
    | BreakInLoop
    | ReturnInLoop
    | MatchStatement
    | DelStatement
    | TryBlock
    | ExceptionBaseHandler
    | RaiseWithoutCause
    | StaticMethod
    | ClassMethod
    | PrivateClass
    | DataclassDecorator
    | ProtocolClass
    | RuntimeCheckable
    | AbcBase
    | HandwrittenInit
    | PostInit
    | ClassVarAnnotation
    | OperatorOverload
    | FunctionShape
    | MutableDefault
    | MutableModuleGlobal
    | GlobalStatement
    | ModuleLevelCall
    | SysPathMutation
    | OsEnviron
    | LambdaInCollection
    | InlineAnnotated
    | FutureAnnotations
    | AnyAnnotation
    | TypeAliasAnnotation
    | Comment
    | Docstring
    | AsyncioGather
    | AsyncioToThread
)


@dataclass(frozen=True, slots=True)
class Fact:
    line: int
    symbol: str | None
    detail: FactDetail


@dataclass(frozen=True, slots=True)
class ModuleFacts:
    path: str
    line_count: int
    facts: tuple[Fact, ...]

    @property
    def counts(self) -> Mapping[FactKind, int]:
        tally = Counter(fact.detail.kind for fact in self.facts)
        return MappingProxyType(dict(sorted(tally.items())))


@dataclass(frozen=True, slots=True)
class FactsReport:
    modules: tuple[ModuleFacts, ...]
    unparsable: tuple[UnparsableSource, ...]


class NodeDetector(Protocol):
    def __call__(self, node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]: ...


class FactCollector(Protocol):
    def __call__(self, module: ParsedModule) -> Iterator[Fact]: ...
