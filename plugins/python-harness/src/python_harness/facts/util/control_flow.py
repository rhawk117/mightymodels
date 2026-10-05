"""Branch and loop shapes: else branches, infinite loops, loop exits, match and del."""

import ast
from collections.abc import Iterator, Mapping
from types import MappingProxyType

from python_harness.facts.domain import (
    AncestorChain,
    BreakInLoop,
    DelStatement,
    ElseBranch,
    Fact,
    MatchStatement,
    NodeDetector,
    ReturnInLoop,
    WhileTrue,
)
from python_harness.facts.util.shapes import elif_branch, is_within_loop_body
from python_harness.facts.util.traversal import symbol_of

type ElseOwner = ast.If | ast.For | ast.AsyncFor | ast.While | ast.Try | ast.TryStar

ELSE_OWNER_KEYWORDS: Mapping[type[ElseOwner], str] = MappingProxyType(
    {
        ast.If: 'if',
        ast.For: 'for',
        ast.AsyncFor: 'for',
        ast.While: 'while',
        ast.Try: 'try',
        ast.TryStar: 'try',
    }
)
ELSE_OWNER_TYPES = tuple(ELSE_OWNER_KEYWORDS)


def else_branch_of(owner: ElseOwner) -> list[ast.stmt]:
    if isinstance(owner, ast.If) and elif_branch(owner) is not None:
        return []
    return owner.orelse


def is_true_constant(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is True


def detect_else_branch(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if not isinstance(node, ELSE_OWNER_TYPES):
        return
    branch = else_branch_of(node)
    if branch:
        statement = ELSE_OWNER_KEYWORDS[type(node)]
        yield Fact(branch[0].lineno, symbol_of(node, ancestors), ElseBranch(statement))


def detect_while_true(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.While) and is_true_constant(node.test):
        yield Fact(node.lineno, symbol_of(node, ancestors), WhileTrue())


def detect_break_in_loop(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.Break):
        yield Fact(node.lineno, symbol_of(node, ancestors), BreakInLoop())


def detect_return_in_loop(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.Return) and is_within_loop_body(node, ancestors):
        yield Fact(node.lineno, symbol_of(node, ancestors), ReturnInLoop())


def detect_match_statement(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.Match):
        yield Fact(node.lineno, symbol_of(node, ancestors), MatchStatement())


def detect_del_statement(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if isinstance(node, ast.Delete):
        yield Fact(node.lineno, symbol_of(node, ancestors), DelStatement())


CONTROL_FLOW_DETECTORS: tuple[NodeDetector, ...] = (
    detect_else_branch,
    detect_while_true,
    detect_break_in_loop,
    detect_return_in_loop,
    detect_match_statement,
    detect_del_statement,
)
