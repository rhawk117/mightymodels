import argparse
import sys
from pathlib import Path

from ai_engineer_cli.findings import CannotCheckError, Finding, report
from ai_engineer_cli.frontmatter import parse_skill_text
from ai_engineer_cli.instruction_audit import audit_files
from ai_engineer_cli.instruction_files import discover, read_text
from ai_engineer_cli.rule_body import check_body
from ai_engineer_cli.rule_fields import check_frontmatter


def build_group(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser(
        'validate',
        help='check a .claude/rules rule file, or audit the instruction files of a project',
    )
    validate.add_argument(
        'path',
        type=Path,
        metavar='PATH',
        help='a rule .md file, or a project directory holding CLAUDE.md and .claude/rules',
    )
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)


def validate_command(arguments: argparse.Namespace) -> int:
    """Return 0 for a pass, 1 for findings, 2 when the check could not run."""
    path = arguments.path
    try:
        findings = audit_project(path) if path.is_dir() else check_rule_file(path)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    return report(path.resolve().name, findings, strict=arguments.strict)


def check_rule_file(path: Path) -> list[Finding]:
    if not path.is_file():
        message = f'{path} is not a file or a directory'
        raise CannotCheckError(message)
    return check_rule(read_text(path))


def check_rule(text: str) -> list[Finding]:
    """The checks on one rule file: the built-in opens none of them."""
    rule = parse_skill_text(text)
    return [*check_frontmatter(rule), *check_body(rule.body)]


def audit_project(root: Path) -> list[Finding]:
    files = discover(root)
    rule_findings = [
        Finding(finding.level, f'{entry.relative}: {finding.message}')
        for entry in files
        if not entry.always_on
        for finding in check_rule(entry.text)
    ]
    return [*rule_findings, *audit_files(files, root)]
