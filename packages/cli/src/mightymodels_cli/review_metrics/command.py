"""The `mightymodels review-metrics` command: the mechanical layer of a code-quality review.

It measures the Python, JavaScript and TypeScript files under a root:

- function size, parameter counts, boolean flag parameters and nesting depth;
- file size and long lines;
- Martin's component metrics per package: fan-in, fan-out, instability, abstractness and
  distance from the main sequence;
- dependency cycles between modules and between packages;
- test presence and the ratio of test to source lines.

    mightymodels review-metrics ROOT [--out FILE] [--max-listed N] [--package-depth N]

The summary goes to standard output. With `--out` the whole report is also written to FILE as
JSON, through the codec, and the first line printed names that file. A root that is not a
directory ends the command with the reason on standard error and the exit code that says
refused. The parser is in `main` and the measuring is in this package.
"""

import sys
from typing import TYPE_CHECKING

from mightymodels_core.primitives.codec import encode_indented
from mightymodels_core.primitives.errors import StateError

from mightymodels_cli.verify import refused

from .components import build_module_graph
from .shapes import SummaryOptions
from .sources import collect_metrics
from .summary import render_summary, summarize

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


class RootNotDirectoryError(StateError):
    def __init__(self, root: Path) -> None:
        super().__init__(f'{root} is not a directory')


def review_metrics(arguments: argparse.Namespace) -> int:
    root = arguments.root.resolve()
    if not root.is_dir():
        return refused(RootNotDirectoryError(root))

    metrics = collect_metrics(root)
    report = summarize(
        metrics,
        build_module_graph(metrics),
        SummaryOptions(cap=arguments.max_listed, depth=arguments.package_depth),
    )
    if arguments.out is not None:
        arguments.out.write_bytes(encode_indented(report))
        sys.stdout.write(f'wrote {arguments.out}\n')
    sys.stdout.write(render_summary(report) + '\n')
    return 0
