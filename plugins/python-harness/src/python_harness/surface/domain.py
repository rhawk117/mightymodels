"""What a review covers and how its modules divide into import-graph clusters."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from python_harness.core.sources import UnparsableSource
from python_harness.imports.domain import ImportGraph


@dataclass(frozen=True, slots=True)
class CodebaseTarget:
    paths: tuple[str, ...] = ('.',)
    kind: Literal['codebase'] = field(default='codebase', init=False)


@dataclass(frozen=True, slots=True)
class DiffTarget:
    base: str
    head: str = 'HEAD'
    kind: Literal['diff'] = field(default='diff', init=False)


type Target = CodebaseTarget | DiffTarget


@dataclass(frozen=True, slots=True)
class SurfaceOptions:
    max_cluster_lines: int = 1200
    dispatch_budget: int = 24


@dataclass(frozen=True, slots=True)
class SurfaceGraph:
    graph: ImportGraph
    surface: frozenset[str]
    line_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ClusterModule:
    path: str
    module: str
    lines: int


@dataclass(frozen=True, slots=True)
class Cluster:
    id: str
    modules: tuple[ClusterModule, ...]
    tests: tuple[str, ...]
    dependents: tuple[str, ...]

    @property
    def lines(self) -> int:
        return sum(item.lines for item in self.modules)


@dataclass(frozen=True, slots=True)
class SurfacePlan:
    target: Target
    clusters: tuple[Cluster, ...]
    unparsable: tuple[UnparsableSource, ...]
    options: SurfaceOptions

    @property
    def module_count(self) -> int:
        return sum(len(cluster.modules) for cluster in self.clusters)

    @property
    def line_count(self) -> int:
        return sum(cluster.lines for cluster in self.clusters)

    @property
    def dispatches(self) -> int:
        return len(self.clusters)

    @property
    def over_budget(self) -> bool:
        return self.dispatches > self.options.dispatch_budget
