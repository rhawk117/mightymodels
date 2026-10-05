"""Import graphs built from importer and imported pairs, for clustering scenarios."""

from collections.abc import Iterable
from itertools import chain
from types import MappingProxyType

from python_harness.imports.domain import ImportEdge, ImportGraph, ModuleRef


def graph_from_links(links: Iterable[tuple[str, str]]) -> ImportGraph:
    edges = tuple(ImportEdge(importer, imported, 1) for importer, imported in links)
    ends = chain.from_iterable((edge.importer, edge.imported) for edge in edges)
    names = sorted(set(ends))
    modules = {name: ModuleRef(name, f'{name}.py', is_test=False) for name in names}
    return ImportGraph(MappingProxyType(modules), (), edges)
