"""The `mightymodels` command line: one argparse tree, one branch per command."""

import argparse
from typing import TYPE_CHECKING

from mightymodels_cli.review_signals.command import review_signals
from mightymodels_cli.verify import verify_run

if TYPE_CHECKING:
    from collections.abc import Sequence

VERIFY_COMMAND = 'verify'
RUN_COMMAND = 'run'
REVIEW_SIGNALS_COMMAND = 'review-signals'
CODE_CHURN_REPORT = 'code-churn'
CHANGE_COUPLING_REPORT = 'change-coupling'
CODE_HOTSPOTS_REPORT = 'code-hotspots'
DEFAULT_MAX_COMMITS = 500
DEFAULT_LIMIT = 25
DEFAULT_MIN_SHARED = 3
DEFAULT_MAX_CHANGESET = 50
PHASES = ('planning', 'task', 'review', 'landing')
DEFAULT_PHASE = 'task'


def add_verify_run(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    verify = commands.add_parser(VERIFY_COMMAND, help='run approved verification commands')
    actions = verify.add_subparsers(dest='action', required=True)
    run = actions.add_parser(RUN_COMMAND, help='run approved contract commands by id')
    run.add_argument('--slug', required=True, help='the ticket whose contract approved them')
    chosen = run.add_mutually_exclusive_group(required=True)
    chosen.add_argument('--id', action='append', help='an approved command id; repeatable')
    chosen.add_argument('--all', action='store_true', help='every approved command')
    run.add_argument('--phase', choices=PHASES, default=DEFAULT_PHASE)


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        message = 'must be at least 1'
        raise argparse.ArgumentTypeError(message)
    return value


def add_window(sub: argparse.ArgumentParser) -> None:
    sub.add_argument('--target', help='file or directory, relative to the repository')
    sub.add_argument('--since', help='git date, e.g. 2026-01-01 or "6 months ago"')
    sub.add_argument('--baseline-ref', help='only commits after this ref, up to HEAD')
    size = sub.add_mutually_exclusive_group()
    size.add_argument('--max-commits', type=positive, default=DEFAULT_MAX_COMMITS)
    size.add_argument('--all-history', action='store_true')
    sub.add_argument('--limit', type=positive, default=DEFAULT_LIMIT)


def add_review_signals(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    signals = commands.add_parser(
        REVIEW_SIGNALS_COMMAND,
        help='measure git history for a review: churn, change coupling, hotspots',
    )
    reports = signals.add_subparsers(dest='analysis', required=True)
    churn = reports.add_parser(CODE_CHURN_REPORT, help='commits and lines changed per file')
    coupling = reports.add_parser(
        CHANGE_COUPLING_REPORT, help='files that change in the same commits'
    )
    coupling.add_argument('--min-shared', type=positive, default=DEFAULT_MIN_SHARED)
    coupling.add_argument('--max-changeset', type=positive, default=DEFAULT_MAX_CHANGESET)
    hotspots = reports.add_parser(
        CODE_HOTSPOTS_REPORT, help='churn weighted by indentation complexity'
    )
    for sub in (churn, coupling, hotspots):
        add_window(sub)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='mightymodels', description='mightymodels command line tools.'
    )
    commands = parser.add_subparsers(dest='command', required=True)
    add_verify_run(commands)
    add_review_signals(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == REVIEW_SIGNALS_COMMAND:
        return review_signals(arguments)

    return verify_run(arguments)
