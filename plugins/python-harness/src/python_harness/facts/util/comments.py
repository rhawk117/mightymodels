"""Comments read from tokens and docstrings read from the tree, each with its owner."""

import ast
import io
import tokenize
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from operator import attrgetter
from types import MappingProxyType

from python_harness.core.sources import ParsedModule
from python_harness.core.syntax import DEFINITION_TYPES
from python_harness.facts.domain import AncestorChain, Comment, Docstring, Fact, NodeDetector
from python_harness.facts.util.traversal import (
    qualified_name,
    symbol_of,
    walk_with_ancestors,
)

type Documented = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef

DOCSTRING_OWNERS: Mapping[type[Documented], str] = MappingProxyType(
    {
        ast.Module: 'module',
        ast.ClassDef: 'class',
        ast.FunctionDef: 'function',
        ast.AsyncFunctionDef: 'function',
    }
)
DOCUMENTED_TYPES = tuple(DOCSTRING_OWNERS)


@dataclass(frozen=True, slots=True)
class SymbolSpan:
    symbol: str
    first_line: int
    last_line: int

    def contains(self, line: int) -> bool:
        return self.first_line <= line <= self.last_line


def symbol_spans(tree: ast.Module) -> Iterator[SymbolSpan]:
    for node, ancestors in walk_with_ancestors(tree):
        if isinstance(node, DEFINITION_TYPES):
            last_line = node.end_lineno or node.lineno
            yield SymbolSpan(qualified_name(node, ancestors), node.lineno, last_line)


def symbol_at_line(spans: tuple[SymbolSpan, ...], line: int) -> str | None:
    containing = (span for span in spans if span.contains(line))
    innermost = max(containing, key=attrgetter('first_line'), default=None)
    return None if innermost is None else innermost.symbol


def comment_tokens(text: str) -> Iterator[tokenize.TokenInfo]:
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    return (token for token in tokens if token.type == tokenize.COMMENT)


def observe_comment(token: tokenize.TokenInfo, spans: tuple[SymbolSpan, ...]) -> Fact:
    line = token.start[0]
    text = token.string.removeprefix('#').strip()
    return Fact(line, symbol_at_line(spans, line), Comment(text))


def docstring_of(owner: Documented) -> ast.Expr | None:
    first = owner.body[0] if owner.body else None
    if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
        return None
    return first if isinstance(first.value.value, str) else None


def detect_docstring(node: ast.AST, ancestors: AncestorChain) -> Iterator[Fact]:
    if not isinstance(node, DOCUMENTED_TYPES):
        return
    docstring = docstring_of(node)
    if docstring is not None:
        owner = DOCSTRING_OWNERS[type(node)]
        yield Fact(docstring.lineno, symbol_of(node, ancestors), Docstring(owner))


def collect_comment_facts(module: ParsedModule) -> Iterator[Fact]:
    spans = tuple(symbol_spans(module.tree))
    comments = comment_tokens(module.source.text)
    return (observe_comment(token, spans) for token in comments)


DOCSTRING_DETECTORS: tuple[NodeDetector, ...] = (detect_docstring,)
