"""The review_metrics use cases: read the run in a short unit, then measure off the loop.

`locate_metrics` reads the run in one unit and closes it. `write_metrics` holds no unit, so the
tool runs it in a worker thread after leaving the unit.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.units_of_work import ReviewWork

from mightymodels_mcp.server.state import create_work

from .components import build_module_graph
from .domain import SummaryOptions
from .errors import MetricsWriteError
from .sources import collect_metrics
from .summary import render_summary, summarize

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import RunId
    from mightymodels_core.workspace import Workspace

    from .schemas import ReviewMetricsRequest

METRICS_FILE = 'uncle-bob-metrics.json'
JSON_INDENT = 2


@dataclass(slots=True, kw_only=True, frozen=True)
class MetricsTarget:
    root: Path
    directory: Path
    relative: str
    options: SummaryOptions


def create_metrics_work(state: OpenState) -> ReviewWork:
    return create_work(state, ReviewWork)


def locate_metrics(
    work: ReviewWork, workspace: Workspace, request: ReviewMetricsRequest
) -> MetricsTarget:
    run_id: RunId = request.run_id
    with work.read() as unit:
        run = unit.reviews.report(run_id).run

    directory = workspace.review_directory(run.slug, run_id)
    return MetricsTarget(
        root=workspace.root,
        directory=directory,
        relative=workspace.relative_to_root(directory),
        options=SummaryOptions(cap=request.max_listed, depth=request.package_depth),
    )


def write_metrics(target: MetricsTarget) -> str:
    metrics = collect_metrics(target.root)
    report = summarize(metrics, build_module_graph(metrics), target.options)
    try:
        target.directory.mkdir(parents=True, exist_ok=True)
        target.directory.joinpath(METRICS_FILE).write_text(
            report.model_dump_json(indent=JSON_INDENT), encoding='utf-8'
        )
    except OSError as error:
        raise MetricsWriteError(
            path=f'{target.relative}/{METRICS_FILE}', reason=error.strerror or str(error)
        ) from error
    return f'wrote {target.relative}/{METRICS_FILE}\n{render_summary(report)}\n'
