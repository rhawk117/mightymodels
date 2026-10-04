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
from ai_engineer_cli.plugin.record import decode_plan, unknown_keys


def build_group(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser('validate', help='check a plugin plan record')
    validate.add_argument('plan', type=Path, metavar='PLAN', help='plan record JSON')
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)


def validate_command(arguments: argparse.Namespace) -> int:
    """Return 0 for a pass, 1 for findings, 2 when the record cannot be read."""
    path = arguments.plan
    try:
        text = read_text(path)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    try:
        document = msgspec.json.decode(text)
    except msgspec.DecodeError as problem:
        print(f'error: {path} is not valid JSON: {problem}', file=sys.stderr)
        return 2
    return report(str(path), validate_findings(text, document), strict=arguments.strict)


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
