"""Detector catalogs, expectation aliases and observations shared by the facts tests."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from python_harness.facts.domain import Fact, NodeDetector
from python_harness.facts.services import FactCatalog

if TYPE_CHECKING:
    from python_harness.facts.domain import FactDetail, FactKind

type KindAndLine = tuple[FactKind, int]
type KindsAndLines = tuple[KindAndLine, ...]
type Details = tuple[FactDetail, ...]


def kinds_and_lines(facts: Iterable[Fact]) -> list[KindAndLine]:
    return sorted((fact.detail.kind, fact.line) for fact in facts)


def details_sharing_kinds(facts: Iterable[Fact], expected: Details) -> Details:
    kinds = frozenset(detail.kind for detail in expected)
    return tuple(fact.detail for fact in facts if fact.detail.kind in kinds)


def build_detector_catalog(detectors: tuple[NodeDetector, ...]) -> FactCatalog:
    return FactCatalog(node_detectors=detectors, module_collectors=())
