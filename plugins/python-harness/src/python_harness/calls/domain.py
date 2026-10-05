"""Where top-level symbols are referenced across a project, and module coupling facts."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum, auto
from itertools import chain
from types import MappingProxyType

from python_harness.core.sources import ParsedModule, UnparsableSource
from python_harness.imports.domain import ImportBinding, ImportGraph


class SymbolKind(StrEnum):
    FUNCTION = auto()
    CLASS = auto()
    CONSTANT = auto()


class ReferenceContext(StrEnum):
    CALL = auto()
    IMPORT = auto()
    ANNOTATION = auto()
    NAME = auto()


type ContextCounts = Mapping[ReferenceContext, int]


@dataclass(frozen=True, slots=True, order=True)
class Reference:
    path: str
    line: int
    context: ReferenceContext


@dataclass(frozen=True, slots=True)
class SymbolDefinition:
    module: str
    path: str
    name: str
    kind: SymbolKind
    line: int

    @property
    def is_public(self) -> bool:
        return not self.name.startswith('_')

    def qualified_name(self) -> str:
        return f'{self.module}.{self.name}'

    def matches(self, requested: str) -> bool:
        return requested in {self.name, self.qualified_name()}


@dataclass(frozen=True, slots=True)
class SymbolUsage:
    definition: SymbolDefinition
    references: tuple[Reference, ...]

    @property
    def reference_count(self) -> int:
        return len(self.references)

    @property
    def referencing_paths(self) -> tuple[str, ...]:
        defining_path = self.definition.path
        elsewhere = {item.path for item in self.references if item.path != defining_path}
        return tuple(sorted(elsewhere))

    @property
    def context_counts(self) -> ContextCounts:
        counted = Counter(item.context for item in self.references)
        present = (context for context in ReferenceContext if context in counted)
        return MappingProxyType({context: counted[context] for context in present})


@dataclass(frozen=True, slots=True)
class SymbolSummary:
    name: str
    kind: SymbolKind
    line: int
    referencing_paths: tuple[str, ...]
    context_counts: ContextCounts


@dataclass(frozen=True, slots=True)
class ModuleScope:
    name: str
    module: ParsedModule
    bindings: tuple[ImportBinding, ...]
    symbols: tuple[SymbolDefinition, ...]

    @property
    def path(self) -> str:
        return self.module.source.path

    @property
    def local_names(self) -> Mapping[str, str]:
        imported = {item.local_name: item.bound_name for item in self.bindings if not item.is_star}
        defined = {item.name: item.qualified_name() for item in self.symbols}
        return MappingProxyType(imported | defined)


@dataclass(frozen=True, slots=True)
class TargetedProject:
    graph: ImportGraph
    scopes: Mapping[str, ModuleScope]
    targets: tuple[ModuleScope, ...]
    unparsable: tuple[UnparsableSource, ...]

    @property
    def definitions(self) -> tuple[SymbolDefinition, ...]:
        return tuple(chain.from_iterable(scope.symbols for scope in self.targets))


@dataclass(frozen=True, slots=True)
class ModuleMetrics:
    path: str
    module: str
    fan_in: int
    fan_out: int
    public_symbols: int
    private_symbols: int
    function_count: int
    max_function_statements: int
    max_parameters: int
    test_paths: tuple[str, ...]

    @property
    def instability(self) -> float | None:
        coupling = self.fan_in + self.fan_out
        if coupling == 0:
            return None
        return self.fan_out / coupling


@dataclass(frozen=True, slots=True)
class ModuleCalls:
    metrics: ModuleMetrics
    external: tuple[SymbolSummary, ...]
    internal_only: tuple[str, ...]
    unreferenced: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CallsReport:
    modules: tuple[ModuleCalls, ...]
    unparsable: tuple[UnparsableSource, ...]


@dataclass(frozen=True, slots=True)
class SymbolReferencesReport:
    name: str
    symbols: tuple[SymbolUsage, ...]
    unparsable: tuple[UnparsableSource, ...]
