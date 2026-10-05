"""Entry point for the `python-harness` command line; a group loads only when it runs."""

import argparse
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import TextIO

from python_harness.cli.domain import (
    ArgumentRegistrar,
    GroupDefinition,
    GroupName,
    ProcessEdge,
)
from python_harness.cli.exit_codes import ExitCode
from python_harness.core.errors import PythonHarnessError


def load_inspect_group() -> ArgumentRegistrar:
    from python_harness.cli.inspection import register_inspect_commands  # noqa: PLC0415  loads with its group.

    return register_inspect_commands


def load_hooks_group() -> ArgumentRegistrar:
    from python_harness.cli.hooks import register_hooks_commands  # noqa: PLC0415  loads with its group.

    return register_hooks_commands


def default_groups() -> Mapping[GroupName, GroupDefinition]:
    return MappingProxyType(
        {
            GroupName.INSPECT: GroupDefinition(
                'facts about a Python project, as JSON', load_inspect_group
            ),
            GroupName.HOOKS: GroupDefinition(
                'Claude Code hook handlers: event JSON on stdin, hook JSON on stdout',
                load_hooks_group,
            ),
        }
    )


def requested_groups(argv: Sequence[str]) -> frozenset[str]:
    first = next((argument for argument in argv if not argument.startswith('-')), None)
    return frozenset(() if first is None else (first,))


def build_parser(loaded: Iterable[str]) -> argparse.ArgumentParser:
    chosen = frozenset(loaded)
    parser = argparse.ArgumentParser(
        prog='python-harness',
        description='Python engineering tools for the python-harness plugin.',
    )
    commands = parser.add_subparsers(dest='group', required=True)
    for name, definition in default_groups().items():
        group = commands.add_parser(name, help=definition.summary)
        if name in chosen:
            definition.load()(group)
    return parser


def discard_further_output(stream: TextIO) -> None:
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, stream.fileno())
    os.close(devnull)


def main(argv: Sequence[str] | None = None, *, edge: ProcessEdge | None = None) -> int:
    chosen = ProcessEdge(sys.stdin, sys.stdout, sys.stderr, os.environ) if edge is None else edge
    arguments_given = sys.argv[1:] if argv is None else argv
    parser = build_parser(requested_groups(arguments_given))
    arguments = parser.parse_args(arguments_given)
    try:
        exit_code = ExitCode(arguments.handler(arguments, chosen))
        chosen.stdout.flush()
    except PythonHarnessError as error:
        chosen.stderr.write(f'python-harness: {error}\n')
        return ExitCode.ERROR
    except BrokenPipeError:
        discard_further_output(chosen.stdout)
        return ExitCode.PASSED
    return exit_code
