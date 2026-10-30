"""The one table that picks what to do with a source file by its language."""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from .files import JS_SUFFIXES, TS_SUFFIXES
from .python_source import analyze_python
from .script_source import ScriptDialect, analyze_js

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .domain import FileMetric, Language


def resolve_python_internal(imp: str, lookup: dict[str, str]) -> str | None:
    candidate = imp
    while candidate and candidate not in lookup:
        candidate = candidate.rpartition('.')[0]
    return lookup[candidate] if candidate else None


def normalized_parts(parts: tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for part in parts:
        if part == '..':
            normalized = normalized[:-1]
            continue
        if part not in {'.', ''}:
            normalized.append(part)
    return normalized


def resolve_javascript_internal(imp: str, metric: FileMetric, lookup: dict[str, str]) -> str | None:
    if not imp.startswith('.'):
        return None
    joined = Path(metric.path).parent.joinpath(imp)
    if joined.suffix in JS_SUFFIXES | TS_SUFFIXES:
        joined = joined.with_suffix('')
    parts = normalized_parts(joined.parts)
    if parts and parts[-1] == 'index':
        parts = parts[:-1]
    return lookup.get('.'.join(parts))


class SourceLanguage(Protocol):
    def analyze(self, rel: Path, text: str) -> FileMetric: ...

    def resolve_import(
        self, imp: str, metric: FileMetric, lookup: dict[str, str], /
    ) -> str | None: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class PythonLanguage:
    def analyze(self, rel: Path, text: str) -> FileMetric:
        return analyze_python(rel, text)

    def resolve_import(self, imp: str, _metric: FileMetric, lookup: dict[str, str]) -> str | None:
        return resolve_python_internal(imp, lookup)


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptLanguage:
    dialect: ScriptDialect

    def analyze(self, rel: Path, text: str) -> FileMetric:
        return analyze_js(rel, text, self.dialect)

    def resolve_import(self, imp: str, metric: FileMetric, lookup: dict[str, str]) -> str | None:
        return resolve_javascript_internal(imp, metric, lookup)


SOURCE_LANGUAGES: Mapping[Language, SourceLanguage] = MappingProxyType({
    'python': PythonLanguage(),
    'javascript': ScriptLanguage(dialect=ScriptDialect(name='javascript', typed=False)),
    'typescript': ScriptLanguage(dialect=ScriptDialect(name='typescript', typed=True)),
})
