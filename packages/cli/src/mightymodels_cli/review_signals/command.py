"""The `mightymodels review-signals` edge: one `git log` read, one JSON document written.

    mightymodels review-signals code-churn [--target PATH] [WINDOW] [--limit N]
    mightymodels review-signals change-coupling [--target PATH] [WINDOW] [--min-shared N]
        [--max-changeset N] [--limit N]
    mightymodels review-signals code-hotspots [--target PATH] [WINDOW] [--limit N]

WINDOW is any of --since DATE, --baseline-ref REF, and --max-commits N or --all-history. A
refusal goes to standard error as one line and the exit code says refused.
"""

import asyncio
import sys
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from mightymodels_core.primitives.codec import encode_indented

from mightymodels_cli.verify import refused

from .history import Analysis, SignalsError, create_git_source, load_history
from .reports import change_coupling, code_churn, code_hotspots

if TYPE_CHECKING:
    import argparse

    from .history import GitSource

REPORTS = MappingProxyType({
    Analysis.CHURN: code_churn,
    Analysis.COUPLING: change_coupling,
    Analysis.HOTSPOTS: code_hotspots,
})


async def write_report(arguments: argparse.Namespace, git: GitSource) -> int:
    try:
        history = await load_history(arguments, git)
    except SignalsError as error:
        return refused(error)

    report = REPORTS[Analysis(arguments.analysis)](history, arguments)
    sys.stdout.buffer.write(encode_indented(report) + b'\n')
    return 0


def review_signals(arguments: argparse.Namespace) -> int:
    return asyncio.run(write_report(arguments, create_git_source(Path.cwd())))
