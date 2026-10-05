"""Dividing a review surface into import-graph clusters and the modules around them."""

import ast
from collections import deque
from collections.abc import Iterable, Mapping
from itertools import chain
from types import MappingProxyType

from python_harness.core.sources import ParsedModule
from python_harness.imports.domain import ImportGraph, ModuleRef
from python_harness.surface.domain import Cluster, ClusterModule, SurfaceGraph, SurfaceOptions

type ModuleGroups = tuple[tuple[str, ...], ...]
type Adjacency = Mapping[str, tuple[str, ...]]


def statements_after_docstring(tree: ast.Module) -> tuple[ast.stmt, ...]:
    if ast.get_docstring(tree, clean=False) is None:
        return tuple(tree.body)
    return tuple(tree.body[1:])


def select_paths_with_code(
    modules: Iterable[ParsedModule], surface_paths: frozenset[str]
) -> frozenset[str]:
    with_code = (item for item in modules if statements_after_docstring(item.tree))
    return surface_paths.intersection(item.source.path for item in with_code)


def link_surface_modules(graph: ImportGraph, surface: frozenset[str]) -> Adjacency:
    linked: dict[str, set[str]] = {module: set() for module in surface}
    inside = (edge for edge in graph.edges if edge.importer in surface and edge.imported in surface)
    for edge in inside:
        linked[edge.importer].add(edge.imported)
        linked[edge.imported].add(edge.importer)
    ordered = {module: tuple(sorted(partners)) for module, partners in linked.items()}
    return MappingProxyType(ordered)


def walk_breadth_first(start: str, adjacency: Adjacency) -> tuple[str, ...]:
    order: list[str] = []
    seen = {start}
    pending = deque((start,))
    while pending:
        module = pending.popleft()
        order.append(module)
        unseen = tuple(item for item in adjacency[module] if item not in seen)
        seen.update(unseen)
        pending.extend(unseen)
    return tuple(order)


def find_components(adjacency: Adjacency) -> ModuleGroups:
    components: list[tuple[str, ...]] = []
    placed: set[str] = set()
    for module in sorted(adjacency):
        if module in placed:
            continue
        component = walk_breadth_first(module, adjacency)
        placed.update(component)
        components.append(component)
    return tuple(components)


def pack_in_order(
    modules: Iterable[str], line_counts: Mapping[str, int], limit: int
) -> ModuleGroups:
    packs: list[list[str]] = []
    packed_lines = 0
    for module in modules:
        lines = line_counts[module]
        if not packs or packed_lines + lines > limit:
            packs.append([])
            packed_lines = 0
        packs[-1].append(module)
        packed_lines += lines
    return tuple(tuple(pack) for pack in packs)


def cluster_modules(view: SurfaceGraph, *, options: SurfaceOptions | None = None) -> ModuleGroups:
    chosen = SurfaceOptions() if options is None else options
    components = find_components(link_surface_modules(view.graph, view.surface))
    limit = chosen.max_cluster_lines
    packed = (pack_in_order(component, view.line_counts, limit) for component in components)
    return tuple(chain.from_iterable(packed))


def find_importers(graph: ImportGraph, members: tuple[str, ...]) -> tuple[ModuleRef, ...]:
    inside = frozenset(members)
    importers = {edge.importer for edge in graph.edges if edge.imported in inside}
    return tuple(graph.modules[name] for name in sorted(importers - inside))


def select_test_paths(importers: Iterable[ModuleRef]) -> tuple[str, ...]:
    return tuple(sorted(ref.path for ref in importers if ref.is_test))


def select_dependent_paths(
    importers: Iterable[ModuleRef], surface: frozenset[str]
) -> tuple[str, ...]:
    outside = (ref for ref in importers if ref.name not in surface)
    return tuple(sorted(ref.path for ref in outside if not ref.is_test))


def describe_cluster_module(view: SurfaceGraph, module: str) -> ClusterModule:
    return ClusterModule(view.graph.modules[module].path, module, view.line_counts[module])


def assemble_cluster(identifier: str, members: tuple[str, ...], view: SurfaceGraph) -> Cluster:
    importers = find_importers(view.graph, members)
    return Cluster(
        identifier,
        tuple(describe_cluster_module(view, module) for module in members),
        select_test_paths(importers),
        select_dependent_paths(importers, view.surface),
    )


def format_cluster_id(number: int) -> str:
    return f'c{number:02d}'


def assemble_clusters(groups: ModuleGroups, view: SurfaceGraph) -> tuple[Cluster, ...]:
    numbered = enumerate(groups, start=1)
    return tuple(
        assemble_cluster(format_cluster_id(number), members, view) for number, members in numbered
    )
