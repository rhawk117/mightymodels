"""Simple commands of a Bash script at any depth, parsed with tree-sitter-bash.

Commands come from lists, pipelines, subshells, command and process substitutions, and
the bodies of conditionals, loops and functions. Each word keeps its byte span in its
command's source, so one word can be rewritten exactly; a word holding an expansion has
no literal value.
"""

import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from types import MappingProxyType
from typing import TYPE_CHECKING

import tree_sitter_bash
from tree_sitter import Language, Node, Parser

if TYPE_CHECKING:
    from collections.abc import Callable


COMMAND_NODE = 'command'
STRING_CONTENT_NODE = 'string_content'
NAME_FIELD = 'name'
ARGUMENT_FIELD = 'argument'
LINE_CONTINUATION = '\n'
UNQUOTED_ESCAPE = re.compile(r'\\(.)', re.DOTALL)
QUOTED_ESCAPE = re.compile(r'\\([$`"\\\n])')


@dataclass(frozen=True, slots=True)
class Word:
    value: str | None
    raw: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SimpleCommand:
    source: bytes
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return self.source.decode('utf-8', errors='replace')

    def replace_span(self, start: int, end: int, replacement: str) -> str:
        parts = (self.source[:start], replacement.encode(), self.source[end:])
        return b''.join(parts).decode('utf-8', errors='replace')


@dataclass(frozen=True, slots=True)
class Script:
    source: bytes

    def text_of(self, node: Node) -> str:
        span = self.source[node.start_byte : node.end_byte]
        return span.decode('utf-8', errors='replace')


type LiteralReader = Callable[[Node, Script], str | None]


@cache
def bash_parser() -> Parser:
    return Parser(Language(tree_sitter_bash.language()))


def drop_escape(found: re.Match[str]) -> str:
    character = str(found.group(1))
    if character == LINE_CONTINUATION:
        return ''
    return character


def join_literals(parts: Iterable[str | None]) -> str | None:
    collected = tuple(parts)
    texts = tuple(part for part in collected if part is not None)
    if len(texts) != len(collected):
        return None
    return ''.join(texts)


def word_literal(node: Node, script: Script) -> str | None:
    return UNQUOTED_ESCAPE.sub(drop_escape, script.text_of(node))


def raw_string_literal(node: Node, script: Script) -> str | None:
    return script.text_of(node)[1:-1]


def string_literal(node: Node, script: Script) -> str | None:
    if any(child.type != STRING_CONTENT_NODE for child in node.named_children):
        return None
    return QUOTED_ESCAPE.sub(drop_escape, script.text_of(node)[1:-1])


def children_literal(node: Node, script: Script) -> str | None:
    return join_literals(literal_of(child, script) for child in node.children)


def number_literal(node: Node, script: Script) -> str | None:
    return script.text_of(node)


def default_literal_readers() -> Mapping[str, LiteralReader]:
    return MappingProxyType(
        {
            'word': word_literal,
            'raw_string': raw_string_literal,
            'string': string_literal,
            'concatenation': children_literal,
            'command_name': children_literal,
            'number': number_literal,
        }
    )


LITERAL_READERS = default_literal_readers()


def literal_of(node: Node, script: Script) -> str | None:
    reader = LITERAL_READERS.get(node.type)
    if reader is None:
        return None
    return reader(node, script)


def iterate_nodes(root: Node) -> Iterator[Node]:
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.children))


def word_of(node: Node, command: Node, script: Script) -> Word:
    return Word(
        value=literal_of(node, script),
        raw=script.text_of(node),
        start=node.start_byte - command.start_byte,
        end=node.end_byte - command.start_byte,
    )


def simple_command_from(command: Node, script: Script) -> SimpleCommand | None:
    name = command.child_by_field_name(NAME_FIELD)
    if name is None:
        return None
    nodes = (name, *command.children_by_field_name(ARGUMENT_FIELD))
    return SimpleCommand(
        source=script.source[command.start_byte : command.end_byte],
        words=tuple(word_of(node, command, script) for node in nodes),
    )


def parse_simple_commands(source: bytes) -> tuple[SimpleCommand, ...]:
    script = Script(source)
    tree = bash_parser().parse(source)
    nodes = (node for node in iterate_nodes(tree.root_node) if node.type == COMMAND_NODE)
    commands = (simple_command_from(node, script) for node in nodes)
    return tuple(command for command in commands if command is not None)
