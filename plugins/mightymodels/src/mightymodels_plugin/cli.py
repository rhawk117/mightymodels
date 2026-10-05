"""Command line entry point shared by the MCP server start mode, the hooks and `verify run`."""

import argparse
from collections.abc import Sequence

SERVE_COMMAND = 'serve'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='mightymodels', description='mightymodels state server and command line tools.'
    )
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser(SERVE_COMMAND, help='run the state MCP server on standard input and output')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    from mightymodels_plugin.server import serve  # noqa: PLC0415 - importing mcp costs over a second and every hook and --help run would pay it

    serve()
    return 0
