"""Per-module summaries: coupling metrics, and symbols grouped by where they are used."""

from collections.abc import Iterable

from python_harness.calls.domain import ModuleCalls, ModuleScope, SymbolSummary, SymbolUsage
from python_harness.calls.util.metrics import measure_module
from python_harness.calls.util.references import ReferenceIndex, describe_symbol_usage
from python_harness.imports.domain import ImportGraph


def summarize_usage(usage: SymbolUsage) -> SymbolSummary:
    definition = usage.definition
    return SymbolSummary(
        name=definition.name,
        kind=definition.kind,
        line=definition.line,
        referencing_paths=usage.referencing_paths,
        context_counts=usage.context_counts,
    )


def names_of(usages: Iterable[SymbolUsage]) -> tuple[str, ...]:
    return tuple(item.definition.name for item in usages)


def summarize_module(
    scope: ModuleScope, references: ReferenceIndex, graph: ImportGraph
) -> ModuleCalls:
    usages = describe_symbol_usage(scope.symbols, references)
    external = (item for item in usages if item.referencing_paths)
    internal = (item for item in usages if item.references and not item.referencing_paths)
    unreferenced = (item for item in usages if not item.references)
    return ModuleCalls(
        metrics=measure_module(scope, graph),
        external=tuple(summarize_usage(item) for item in external),
        internal_only=names_of(internal),
        unreferenced=names_of(unreferenced),
    )
