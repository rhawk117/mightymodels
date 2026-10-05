"""Reading and parsing Python sources, keeping unparsable files as reportable values."""

import ast
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from python_harness.core.workspace import Workspace


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: str
    text: str

    @property
    def line_count(self) -> int:
        return len(self.text.splitlines())

    def line_range(self, start: int, end: int) -> tuple[str, ...]:
        return tuple(self.text.splitlines()[start - 1 : end])


@dataclass(frozen=True, slots=True)
class ParsedModule:
    source: SourceFile
    tree: ast.Module


@dataclass(frozen=True, slots=True)
class UnparsableSource:
    path: str
    line: int | None
    message: str


type ParseOutcome = ParsedModule | UnparsableSource


@dataclass(frozen=True, slots=True)
class LoadedSources:
    modules: tuple[ParsedModule, ...]
    unparsable: tuple[UnparsableSource, ...]


def read_source(workspace: Workspace, path: Path) -> SourceFile:
    with tokenize.open(workspace.resolve(path)) as stream:
        return SourceFile(workspace.relative(path), stream.read())


def parse_source(source: SourceFile) -> ParseOutcome:
    try:
        tree = ast.parse(source.text, filename=source.path, type_comments=False)
    except SyntaxError as error:
        return UnparsableSource(source.path, error.lineno, error.msg)
    return ParsedModule(source, tree)


def load_source(workspace: Workspace, path: Path) -> ParseOutcome:
    try:
        source = read_source(workspace, path)
    except SyntaxError as error:
        return UnparsableSource(workspace.relative(path), error.lineno, error.msg)
    except (OSError, UnicodeDecodeError) as error:
        return UnparsableSource(workspace.relative(path), None, str(error))
    return parse_source(source)


def load_sources(workspace: Workspace, paths: Iterable[Path]) -> LoadedSources:
    outcomes = tuple(load_source(workspace, path) for path in paths)
    modules = tuple(item for item in outcomes if isinstance(item, ParsedModule))
    unparsable = tuple(item for item in outcomes if isinstance(item, UnparsableSource))
    return LoadedSources(modules, unparsable)
