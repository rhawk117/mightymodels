"""The statement catalogue: `-- name: <name>` blocks of one SQL text, matched to declarations."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import (
    DuplicateBlockError,
    DuplicateDeclarationError,
    EmptyBlockError,
    MissingBlockError,
    UndeclaredBlockError,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from .statements import Declaration

BLOCK_MARKER = re.compile(r'^--[ \t]*name:[ \t]*(?P<name>\S+)[ \t]*$', re.MULTILINE)


def has_sql(block: str) -> bool:
    lines = (line.strip() for line in block.splitlines())
    return any(line and not line.startswith('--') for line in lines)


def parse_blocks(text: str) -> dict[str, str]:
    markers = list(BLOCK_MARKER.finditer(text))
    ends = [marker.start() for marker in markers[1:]] + [len(text)]
    blocks: dict[str, str] = {}
    for marker, end in zip(markers, ends, strict=True):
        name = marker.group('name')
        block = text[marker.end() : end].strip()
        if name in blocks:
            raise DuplicateBlockError(name=name)

        if not has_sql(block):
            raise EmptyBlockError(name=name)

        blocks[name] = block
    return blocks


def index_declarations(declarations: Iterable[Declaration]) -> dict[str, Declaration]:
    indexed: dict[str, Declaration] = {}
    for declaration in declarations:
        if declaration.name in indexed:
            raise DuplicateDeclarationError(name=declaration.name)

        indexed[declaration.name] = declaration
    return indexed


@dataclass(slots=True, kw_only=True, frozen=True)
class Catalogue:
    sql_by_name: Mapping[str, str]

    def sql_for(self, declaration: Declaration) -> str:
        return self.sql_by_name[declaration.name]


def bind_catalogue(text: str, declarations: Iterable[Declaration]) -> Catalogue:
    blocks = parse_blocks(text)
    declared = index_declarations(declarations)
    if missing := sorted(declared.keys() - blocks.keys()):
        raise MissingBlockError(name=missing[0])

    if undeclared := sorted(blocks.keys() - declared.keys()):
        raise UndeclaredBlockError(name=undeclared[0])

    return Catalogue(sql_by_name=blocks)
