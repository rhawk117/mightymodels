"""An import across nested `src` packages counts as fan-out between their components."""

from typing import TYPE_CHECKING

from mightymodels_mcp.review_metrics.components import build_module_graph
from mightymodels_mcp.review_metrics.domain import SummaryOptions
from mightymodels_mcp.review_metrics.sources import collect_metrics
from mightymodels_mcp.review_metrics.summary import summarize

if TYPE_CHECKING:
    from pathlib import Path

PACKAGE_DEPTH = 2


class TestSrcLayoutFanOut:
    TREE = (
        ('packages/a/src/a_pkg/__init__.py', 'from b_pkg import tool\n'),
        ('packages/b/src/b_pkg/__init__.py', 'def tool():\n    return 1\n'),
    )

    def test_an_import_across_nested_src_packages_counts_as_fan_out(self, tmp_path: Path) -> None:
        for name, text in self.TREE:
            path = tmp_path.joinpath(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        metrics = collect_metrics(tmp_path)

        report = summarize(
            metrics, build_module_graph(metrics), SummaryOptions(depth=PACKAGE_DEPTH)
        )

        packages = report.component_metrics.packages
        assert packages['packages.a'].fan_out_ce == 1
        assert packages['packages.b'].fan_in_ca == 1
