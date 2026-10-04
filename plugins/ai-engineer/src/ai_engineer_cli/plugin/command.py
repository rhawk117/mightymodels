import argparse
import sys
from pathlib import Path

import msgspec

from ai_engineer_cli.findings import (
    CannotCheckError,
    Finding,
    decode_problem,
    error,
    report,
    warning,
)
from ai_engineer_cli.jsondoc import duplicate_keys
from ai_engineer_cli.plugin.checks import check_plan
from ai_engineer_cli.plugin.inventory import inventory
from ai_engineer_cli.plugin.manifest import json_text
from ai_engineer_cli.plugin.record import Plan, decode_plan, normalise, unknown_keys
from ai_engineer_cli.plugin.render import RenderRefusedError, render


def build_group(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser('validate', help='check a plugin plan record')
    validate.add_argument('plan', type=Path, metavar='PLAN', help='plan record JSON')
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)
    render_plan = commands.add_parser('render', help='write a plugin shell from a plan record')
    render_plan.add_argument('plan', type=Path, metavar='PLAN', help='plan record JSON')
    render_plan.add_argument('target', type=Path, metavar='TARGET', help='plugin directory')
    render_plan.add_argument(
        '--force', action='store_true', help='rewrite the plan files of an existing plugin'
    )
    render_plan.set_defaults(handler=render_command)
    inventory_plugin = commands.add_parser(
        'inventory', help='record an existing plugin as a plan of built components'
    )
    inventory_plugin.add_argument('plugin_dir', type=Path, metavar='PLUGIN_DIR')
    inventory_plugin.add_argument('--out', type=Path, help='write the record here, not to stdout')
    inventory_plugin.set_defaults(handler=inventory_command)


def validate_command(arguments: argparse.Namespace) -> int:
    """Return 0 for a pass, 1 for findings, 2 when the record cannot be read."""
    try:
        text, document = read_document(arguments.plan)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    return report(str(arguments.plan), validate_findings(text, document), strict=arguments.strict)


def render_command(arguments: argparse.Namespace) -> int:
    """Return 0 once the shell is written, 1 for a record or target it refuses, 2 if unreadable."""
    try:
        text, document = read_document(arguments.plan)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    if report(str(arguments.plan), validate_findings(text, document), strict=False) != 0:
        return 1
    return write_shell(normalise(decode_plan(document)), arguments)


def write_shell(plan: Plan, arguments: argparse.Namespace) -> int:
    try:
        written = render(plan, arguments.target, force=arguments.force)
    except RenderRefusedError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 1
    except OSError as problem:
        print(f'error: could not write under {arguments.target}: {problem}', file=sys.stderr)
        return 2
    for relative in written:
        print(f'wrote {relative}')
    return 0


def inventory_command(arguments: argparse.Namespace) -> int:
    """Return 0 with the record on stdout or in --out, 2 when the plugin cannot be read."""
    plugin_dir = arguments.plugin_dir
    if not plugin_dir.is_dir():
        print(f'error: {plugin_dir} is not a directory', file=sys.stderr)
        return 2
    try:
        text = json_text(msgspec.to_builtins(inventory(plugin_dir)))
        emit_record(text, arguments.out)
    except (msgspec.MsgspecError, OSError, UnicodeError) as problem:
        print(f'error: could not inventory {plugin_dir}: {problem}', file=sys.stderr)
        return 2
    return 0


def emit_record(text: str, out: Path | None) -> None:
    if out is None:
        sys.stdout.write(text)
        return
    out.write_text(text, encoding='utf-8')
    print(f'wrote {out}')


def read_document(path: Path) -> tuple[str, object]:
    text = read_text(path)
    try:
        return text, msgspec.json.decode(text)
    except msgspec.DecodeError as problem:
        message = f'{path} is not valid JSON: {problem}'
        raise CannotCheckError(message) from problem


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read {path}: {problem}'
        raise CannotCheckError(message) from problem


def validate_findings(text: str, document: object) -> list[Finding]:
    findings = [
        error(f'duplicate JSON key {key!r}; the last one wins') for key in duplicate_keys(text)
    ]
    findings += [warning(message) for message in unknown_keys(document)]
    try:
        plan = decode_plan(document)
    except msgspec.ValidationError as problem:
        return [*findings, *decode_problem(problem, builtin_errored=False)]
    return [*findings, *check_plan(plan)]
