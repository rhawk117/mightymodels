"""Command names, the process edge handed to handlers, and seams."""

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Protocol, TextIO

from python_harness.cli.exit_codes import ExitCode

type CommandGroup = argparse._SubParsersAction[argparse.ArgumentParser]  # noqa: SLF001  argparse exposes no public name for the subparsers action type.


class GroupName(StrEnum):
    INSPECT = auto()
    HOOKS = auto()


class InspectCommand(StrEnum):
    SURVEY = auto()
    GATE = auto()


class HookCommand(StrEnum):
    SESSION_START = 'session-start'
    GUARD_PYTHON = 'guard-python'


@dataclass(frozen=True, slots=True)
class ProcessEdge:
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO
    environment: Mapping[str, str]


class CommandHandler(Protocol):
    def __call__(self, arguments: argparse.Namespace, edge: ProcessEdge, /) -> ExitCode: ...


class ArgumentRegistrar(Protocol):
    def __call__(self, parser: argparse.ArgumentParser, /) -> None: ...


class GroupLoader(Protocol):
    def __call__(self) -> ArgumentRegistrar: ...


@dataclass(frozen=True, slots=True)
class GroupDefinition:
    summary: str
    load: GroupLoader


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    summary: str
    handler: CommandHandler
    add_arguments: ArgumentRegistrar | None = None


type InspectCommands = Mapping[InspectCommand, CommandDefinition]
type HookCommands = Mapping[HookCommand, CommandDefinition]
