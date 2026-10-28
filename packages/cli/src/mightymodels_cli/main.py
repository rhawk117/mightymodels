"""The `mightymodels` command line: one argparse tree, one branch per command."""

import argparse
from typing import TYPE_CHECKING

from mightymodels_cli.verify import verify_run

if TYPE_CHECKING:
    from collections.abc import Sequence

VERIFY_COMMAND = 'verify'
RUN_COMMAND = 'run'
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='mightymodels', description='mightymodels command line tools.'
    )
    commands = parser.add_subparsers(dest='command', required=True)
    add_verify_run(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return verify_run(arguments)
