"""The `python-harness hooks` group: Claude Code hook handlers, event JSON in, hook JSON out.

A payload they cannot read is reported on stderr with exit code 1, a non-blocking hook
error to Claude Code; exit code 2 would block the tool call.
"""

import argparse
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING

from python_harness.cli.domain import CommandDefinition, HookCommand, HookCommands, ProcessEdge
from python_harness.cli.exit_codes import ExitCode
from python_harness.cli.util import add_command_parsers
from python_harness.core.errors import PythonHarnessError
from python_harness.core.output import JsonValue, write_document
from python_harness.hooks.domain import HookEvent
from python_harness.hooks.guard.domain import GuardOptions, Nudge
from python_harness.hooks.guard.services import judge_tool_call
from python_harness.hooks.guard.util.presentation import render_note
from python_harness.hooks.schemas import (
    context_document,
    parse_hook_payload,
    parse_session_start,
    parse_tool_call,
)

if TYPE_CHECKING:
    from collections.abc import Callable


type HookAnswer = Callable[[str, Mapping[str, str]], JsonValue | None]

NON_BLOCKING_FAILURE = ExitCode.FAILED


def answer_session_start(payload: str, environment: Mapping[str, str]) -> JsonValue | None:
    from python_harness.hooks.briefing.services import brief_session  # noqa: PLC0415  keeps the scan off the guard's path.

    start = parse_session_start(parse_hook_payload(payload))
    return context_document(HookEvent.SESSION_START, brief_session(start.cwd, environment))


def answer_guard(payload: str, _environment: Mapping[str, str]) -> JsonValue | None:
    options = GuardOptions()
    verdict = judge_tool_call(parse_tool_call(parse_hook_payload(payload)), options)
    if not isinstance(verdict, Nudge):
        return None
    return context_document(HookEvent.PRE_TOOL_USE, render_note(verdict, options))


def run_hook(answer: HookAnswer, edge: ProcessEdge) -> ExitCode:
    try:
        document = answer(edge.stdin.read(), edge.environment)
    except PythonHarnessError as error:
        edge.stderr.write(f'python-harness hooks: {error}\n')
        return NON_BLOCKING_FAILURE
    if document is not None:
        write_document(document, edge.stdout)
    return ExitCode.PASSED


def run_session_start(_arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    return run_hook(answer_session_start, edge)


def run_guard_python(_arguments: argparse.Namespace, edge: ProcessEdge) -> ExitCode:
    return run_hook(answer_guard, edge)


def default_hook_commands() -> HookCommands:
    return MappingProxyType(
        {
            HookCommand.SESSION_START: CommandDefinition(
                'SessionStart: brief the session on the Python toolchain',
                run_session_start,
            ),
            HookCommand.GUARD_PYTHON: CommandDefinition(
                'PreToolUse (Bash): add a note when a command runs plain python',
                run_guard_python,
            ),
        }
    )


def register_hooks_commands(group: argparse.ArgumentParser) -> None:
    commands = group.add_subparsers(dest='command', required=True)
    add_command_parsers(commands, default_hook_commands())
