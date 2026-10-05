"""Command line entry point shared by the MCP server start mode, the hooks and `verify run`."""

import argparse
from collections.abc import Sequence

SERVE_COMMAND = 'serve'
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
        prog='mightymodels', description='mightymodels state server and command line tools.'
    )
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser(SERVE_COMMAND, help='run the state MCP server on standard input and output')
    add_verify_run(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == VERIFY_COMMAND:
        from mightymodels_plugin.commands.verify import verify_run  # noqa: PLC0415 - SQLAlchemy and Pydantic cost up to a second to import and `--help` must not pay it

        return verify_run(arguments)
    from mightymodels_plugin.server import serve  # noqa: PLC0415 - importing mcp costs over a second and every hook and --help run would pay it

    serve()
    return 0
