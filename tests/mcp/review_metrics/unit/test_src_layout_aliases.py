"""Modules under a nested `src` directory are aliased by the path after it."""

from typing import TYPE_CHECKING

from mightymodels_mcp.review_metrics.components import (
    ambiguous_aliases,
    build_module_graph,
    module_lookup,
)
from mightymodels_mcp.review_metrics.shapes import SummaryOptions
from mightymodels_mcp.review_metrics.sources import collect_metrics
from mightymodels_mcp.review_metrics.summary import summarize

if TYPE_CHECKING:
    from pathlib import Path

TREE = {
    'packages/a/src/a_pkg/__init__.py': 'from b_pkg import tool\n',
    'packages/b/src/b_pkg/__init__.py': 'def tool():\n    return 1\n',
}
PACKAGE_DEPTH = 2


def test_a_module_is_aliased_by_the_path_after_any_src_component() -> None:
    lookup = module_lookup(['packages.a.src.a_pkg.mod', 'src.top.mod'])

    assert lookup['a_pkg.mod'] == 'packages.a.src.a_pkg.mod'
    assert lookup['top.mod'] == 'src.top.mod'


def test_an_alias_claimed_by_two_modules_is_dropped_and_reported() -> None:
    names = ['packages.a.src.shared.mod', 'packages.b.src.shared.mod', 'src.top.mod']

    lookup = module_lookup(names)

    assert 'shared.mod' not in lookup
    assert lookup['top.mod'] == 'src.top.mod'
    assert ambiguous_aliases(names) == ['shared.mod']


def test_an_import_across_nested_src_packages_counts_as_fan_out(tmp_path: Path) -> None:
    for name, text in TREE.items():
        path = tmp_path.joinpath(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    metrics = collect_metrics(tmp_path)

    report = summarize(metrics, build_module_graph(metrics), SummaryOptions(depth=PACKAGE_DEPTH))

    packages = report.component_metrics.packages
    assert packages['packages.a'].fan_out_ce == 1
    assert packages['packages.b'].fan_in_ca == 1
