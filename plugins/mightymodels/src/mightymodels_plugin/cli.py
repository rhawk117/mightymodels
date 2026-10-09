"""Command line entry point shared by the MCP server start mode, the hooks and `verify run`."""

import argparse
import os
import sys
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from mightymodels_plugin.commands.dispatch_hook import check_dispatch
from mightymodels_plugin.commands.hook_context import HookContext
from mightymodels_plugin.commands.session_start import export_data_directory

SERVE_COMMAND = 'serve'
SESSION_START_COMMAND = 'session-start'
DISPATCH_HOOK_COMMAND = 'dispatch-hook'
SUBAGENT_RECORD_COMMAND = 'subagent-record'
COMPLETION_GATE_COMMAND = 'completion-gate'
PRE_COMPACT_COMMAND = 'pre-compact'
VERIFY_COMMAND = 'verify'
RUN_COMMAND = 'run'
PHASES = ('planning', 'task', 'review', 'landing')
DEFAULT_PHASE = 'task'
HOOK_MODULES = MappingProxyType(
    {
        SUBAGENT_RECORD_COMMAND: 'mightymodels_plugin.commands.subagent_record',
        COMPLETION_GATE_COMMAND: 'mightymodels_plugin.commands.completion_gate',
        PRE_COMPACT_COMMAND: 'mightymodels_plugin.commands.pre_compact',
    }
)


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
    commands.add_parser(
        SESSION_START_COMMAND,
        help="export the plugin data directory to the session's commands; the SessionStart hook",
    )
    commands.add_parser(
        DISPATCH_HOOK_COMMAND,
        help="deny a worker's dispatch outside its allowed targets; the PreToolUse hook on Agent",
    )
    commands.add_parser(
        SUBAGENT_RECORD_COMMAND,
        help="leave a scout's report in the spool for the state server; the SubagentStop hook",
    )
    commands.add_parser(
        COMPLETION_GATE_COMMAND,
        help="hold an implementer's stop once while its task has no DONE brief; SubagentStop",
    )
    commands.add_parser(
        PRE_COMPACT_COMMAND,
        help='write the snapshot of the ticket on the checked-out branch; the PreCompact hook',
    )
    add_verify_run(commands)
    return parser


def run_hook_command(arguments: argparse.Namespace) -> int | None:
    if arguments.command == SESSION_START_COMMAND:
        return export_data_directory(os.environ)
    if arguments.command == DISPATCH_HOOK_COMMAND:
        return check_dispatch(sys.stdin, sys.stdout)
    if arguments.command not in HOOK_MODULES:
        return None
    hook = import_module(HOOK_MODULES[arguments.command])
    return int(hook.run_hook(HookContext(stdin=sys.stdin, environ=os.environ, cwd=Path.cwd())))


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if (code := run_hook_command(arguments)) is not None:
        return code
    if arguments.command == VERIFY_COMMAND:
        from mightymodels_plugin.commands.verify import verify_run  # noqa: PLC0415 - SQLAlchemy and Pydantic cost up to a second to import and `--help` must not pay it

        return verify_run(arguments)
    from mightymodels_plugin.server import serve  # noqa: PLC0415 - importing mcp costs over a second and every hook and --help run would pay it

    serve()
    return 0
