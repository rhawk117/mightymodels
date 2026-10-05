"""Clustering surface modules by import links and packing large components under a cap."""

from collections.abc import Mapping
from itertools import chain
from types import MappingProxyType

import pytest
from python_harness.imports.domain import ImportGraph
from python_harness.surface.domain import SurfaceGraph, SurfaceOptions
from python_harness.surface.policy import cluster_modules
from python_harness.surface.tests.graphs import graph_from_links


class TestComponents:
    LINES = MappingProxyType(dict.fromkeys('abcdxyz', 10))

    @pytest.mark.parametrize(
        ('graph', 'surface', 'expected'),
        [
            pytest.param(
                graph_from_links((('a', 'b'), ('c', 'd'))),
                frozenset('abcd'),
                (('a', 'b'), ('c', 'd')),
                id='separate-components',
            ),
            pytest.param(
                graph_from_links((('b', 'a'), ('c', 'a'))),
                frozenset('abc'),
                (('a', 'b', 'c'),),
                id='import-direction-ignored',
            ),
            pytest.param(
                graph_from_links((('a', 'b'), ('b', 'a'))),
                frozenset('ab'),
                (('a', 'b'),),
                id='import-cycle',
            ),
            pytest.param(
                graph_from_links((('a', 'x'), ('x', 'b'))),
                frozenset('ab'),
                (('a',), ('b',)),
                id='links-through-modules-outside-the-surface-ignored',
            ),
            pytest.param(
                graph_from_links((('z', 'b'), ('c', 'y'))),
                frozenset('abcyz'),
                (('a',), ('b', 'z'), ('c', 'y')),
                id='ordered-by-alphabetically-first-module',
            ),
        ],
    )
    def test_linked_surface_modules_share_a_cluster(
        self,
        graph: ImportGraph,
        surface: frozenset[str],
        expected: tuple[tuple[str, ...], ...],
    ) -> None:
        assert cluster_modules(SurfaceGraph(graph, surface, self.LINES)) == expected


class TestSplitting:
    OPTIONS = SurfaceOptions(max_cluster_lines=1000)

    @pytest.mark.parametrize(
        ('graph', 'line_counts', 'expected'),
        [
            pytest.param(
                graph_from_links((('a', 'b'), ('b', 'c'), ('c', 'd'))),
                MappingProxyType(dict.fromkeys('abcd', 400)),
                (('a', 'b'), ('c', 'd')),
                id='packs-up-to-the-cap',
            ),
            pytest.param(
                graph_from_links((('a', 'b'),)),
                MappingProxyType(dict.fromkeys('ab', 500)),
                (('a', 'b'),),
                id='exactly-at-the-cap-stays-whole',
            ),
            pytest.param(
                graph_from_links((('a', 'c'), ('c', 'b'))),
                MappingProxyType(dict.fromkeys('abc', 500)),
                (('a', 'c'), ('b',)),
                id='breadth-first-keeps-importers-together',
            ),
            pytest.param(
                graph_from_links((('a', 'b'), ('b', 'c'))),
                MappingProxyType({'a': 100, 'b': 1500, 'c': 100}),
                (('a',), ('b',), ('c',)),
                id='oversize-module-stands-alone',
            ),
            pytest.param(
                graph_from_links((('a', 'b'),)),
                MappingProxyType({'a': 1500, 'b': 100}),
                (('a',), ('b',)),
                id='oversize-first-module-stands-alone',
            ),
        ],
    )
    def test_components_over_the_cap_are_packed_breadth_first(
        self,
        graph: ImportGraph,
        line_counts: Mapping[str, int],
        expected: tuple[tuple[str, ...], ...],
    ) -> None:
        view = SurfaceGraph(graph, frozenset(line_counts), line_counts)

        clusters = cluster_modules(view, options=self.OPTIONS)

        assert clusters == expected


class TestPartition:
    OPTIONS = SurfaceOptions(max_cluster_lines=1000)
    LINES = MappingProxyType({'a': 700, 'b': 300, 'c': 900, 'd': 200, 'e': 1300, 'f': 50, 'g': 450})

    @pytest.mark.parametrize(
        ('graph', 'surface'),
        [
            pytest.param(
                graph_from_links((('a', 'b'), ('a', 'c'), ('a', 'd'), ('a', 'e'))),
                frozenset('abcdefg'),
                id='star-with-isolated-modules',
            ),
            pytest.param(
                graph_from_links((('a', 'b'), ('b', 'c'), ('c', 'a'), ('d', 'e'), ('e', 'f'))),
                frozenset('abcdef'),
                id='cycle-and-chain',
            ),
            pytest.param(
                graph_from_links((('a', 'x'), ('x', 'g'), ('g', 'e'), ('f', 'b'))),
                frozenset('abefg'),
                id='links-leaving-the-surface',
            ),
        ],
    )
    def test_every_surface_module_lands_in_exactly_one_cluster(
        self, graph: ImportGraph, surface: frozenset[str]
    ) -> None:
        view = SurfaceGraph(graph, surface, self.LINES)

        clusters = cluster_modules(view, options=self.OPTIONS)

        assert sorted(chain.from_iterable(clusters)) == sorted(surface)


class TestDeterminism:
    OPTIONS = SurfaceOptions(max_cluster_lines=1000)
    LINES = MappingProxyType(dict.fromkeys('abcdef', 400))
    LINKS = (('d', 'a'), ('a', 'f'), ('f', 'b'), ('c', 'e'), ('b', 'd'))
    SURFACE = frozenset('abcdef')
    FORWARD = SurfaceGraph(graph_from_links(LINKS), SURFACE, LINES)
    BACKWARD = SurfaceGraph(graph_from_links(reversed(LINKS)), SURFACE, LINES)

    def test_link_order_does_not_change_the_clusters(self) -> None:
        forward = cluster_modules(self.FORWARD, options=self.OPTIONS)
        backward = cluster_modules(self.BACKWARD, options=self.OPTIONS)

        assert forward == backward
