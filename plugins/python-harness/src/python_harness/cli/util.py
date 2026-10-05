"""Parser wiring every command group shares: the `--root` option and command tables."""

import argparse
from collections.abc import Mapping
from pathlib import Path

from python_harness.cli.domain import CommandDefinition, CommandGroup


def add_root_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--root', type=Path, default=Path(), help='project root (default: cwd)')


def build_root_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    add_root_option(parent)
    return parent


def add_command_parsers[Name: str](
    commands: CommandGroup,
    definitions: Mapping[Name, CommandDefinition],
    parents: tuple[argparse.ArgumentParser, ...] = (),
) -> None:
    for name, definition in definitions.items():
        parser = commands.add_parser(name, parents=list(parents), help=definition.summary)
        parser.set_defaults(handler=definition.handler)
        if definition.add_arguments is not None:
            definition.add_arguments(parser)
