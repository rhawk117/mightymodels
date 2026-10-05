"""Calls to asyncio.gather and asyncio.to_thread, matched on the dotted callee."""

import ast
from collections.abc import Iterator, Mapping
from types import MappingProxyType

from python_harness.core.syntax import dotted_name
from python_harness.facts.domain import (
    AncestorChain,
    AsyncioGather,
    AsyncioToThread,
    Fact,
    NodeDetector,
)
from python_harness.facts.util.traversal import symbol_of

type AsyncioCall = AsyncioGather | AsyncioToThread

ASYNCIO_CALLS: Mapping[str, AsyncioCall] = MappingProxyType(
    {
        'asyncio.gather': AsyncioGather(),
        'asyncio.to_thread': AsyncioToThread(),
    }
)


def asyncio_call_of(call: ast.Call) -> AsyncioCall | None:
    callee = dotted_name(call.func)
    return None if callee is None else ASYNCIO_CALLS.get(callee)


def detect_asyncio_call(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if not isinstance(node, ast.Call):
        return
    detail = asyncio_call_of(node)
    if detail is not None:
        yield Fact(node.lineno, symbol_of(node, ancestors), detail)


ASYNC_CALL_DETECTORS: tuple[NodeDetector, ...] = (detect_asyncio_call,)
