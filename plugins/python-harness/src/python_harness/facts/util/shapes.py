"""Statement shapes several detectors share: elif chains, loop bodies, mutable values."""

import ast
from itertools import pairwise

from python_harness.core.syntax import dotted_name
from python_harness.facts.domain import AncestorChain
from python_harness.facts.util.traversal import ancestors_within_scope

type LoopOrBranch = ast.For | ast.AsyncFor | ast.While | ast.If

LOOP_TYPES = (ast.For, ast.AsyncFor, ast.While)
MUTABLE_DISPLAY_TYPES = (
    ast.List,
    ast.Dict,
    ast.Set,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
)


def is_in_body(child: ast.AST, owner: LoopOrBranch) -> bool:
    return any(statement is child for statement in owner.body)


def is_within_loop_body(node: ast.AST, ancestors: AncestorChain) -> bool:
    lineage = pairwise((*ancestors_within_scope(ancestors), node))
    return any(
        isinstance(parent, LOOP_TYPES) and is_in_body(child, parent) for parent, child in lineage
    )


def elif_branch(statement: ast.If) -> ast.If | None:
    branch = statement.orelse[0] if len(statement.orelse) == 1 else None
    if isinstance(branch, ast.If) and branch.col_offset == statement.col_offset:
        return branch
    return None


def is_mutable_value(expression: ast.expr, constructors: frozenset[str]) -> bool:
    if isinstance(expression, MUTABLE_DISPLAY_TYPES):
        return True
    return isinstance(expression, ast.Call) and dotted_name(expression.func) in constructors
