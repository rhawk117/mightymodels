import argparse
import sys
import tempfile
from pathlib import Path

from ai_engineer_cli.builtin import run_builtin
from ai_engineer_cli.findings import CannotCheckError, Finding, report
from ai_engineer_cli.hook.checks import check_hooks
from ai_engineer_cli.hook.file import HooksFile, load_hooks_file
from ai_engineer_cli.hook.nodes import SchemaFinding, decode_hooks
from ai_engineer_cli.hook.runner import Expectations, HookTest, check_hook, parse_field_expectation

DEFAULT_TEST_TIMEOUT_SECONDS = 15.0


def build_group(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser(
        'validate',
        help='check the schema, run claude plugin validate, then the checks both miss',
    )
    validate.add_argument(
        'hooks_file',
        type=Path,
        metavar='HOOKS_FILE',
        help='plugin hooks/hooks.json, or a settings file with a top-level hooks key',
    )
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)
    test = commands.add_parser(
        'test',
        help='pipe a payload into a hook script and check the Claude Code output contract',
    )
    test.add_argument('script', type=Path, metavar='SCRIPT', help='hook script to run')
    test.add_argument('payload', type=Path, metavar='PAYLOAD', help='JSON payload file for stdin')
    test.add_argument('--expect-exit', type=int, default=0, help='expected exit code (default 0)')
    test.add_argument(
        '--expect-field',
        action='append',
        default=[],
        type=parse_field_expectation,
        metavar='KEY[=VALUE]',
        help='dotted key that must be in the JSON output, and optionally equal VALUE',
    )
    test.add_argument('--expect-silent', action='store_true', help='expect empty stdout')
    test.add_argument('--malformed', action='store_true', help='send invalid JSON, not the payload')
    test.add_argument('--timeout', type=float, default=DEFAULT_TEST_TIMEOUT_SECONDS)
    test.set_defaults(handler=test_command)


def validate_command(arguments: argparse.Namespace) -> int:
    """Return 0 for a pass, 1 for findings, 2 when the check could not run."""
    path = arguments.hooks_file
    if not path.is_file():
        print(f'error: {path} is not a file', file=sys.stderr)
        return 2
    try:
        findings = validate_findings(path)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    return report(str(path), findings, strict=arguments.strict)


def validate_findings(path: Path) -> list[Finding]:
    """The schema findings, the built-in's the schema did not already report, then the checks."""
    hooks_file = load_hooks_file(path)
    decoded = decode_hooks(hooks_file.config)
    builtin_findings = run_hooks_builtin(hooks_file)
    builtin_errored = any(finding.level == 'error' for finding in builtin_findings)
    own_findings = check_hooks(hooks_file, decoded, builtin_errored=builtin_errored)
    return [
        *(schema_finding.finding for schema_finding in decoded.findings),
        *(
            finding
            for finding in builtin_findings
            if not reports_location(finding, decoded.findings)
        ),
        *own_findings,
    ]


def reports_location(finding: Finding, schema_findings: tuple[SchemaFinding, ...]) -> bool:
    """Whether the finding names a location the schema pass already reported."""
    return any(f'{schema.where}: ' in finding.message for schema in schema_findings)


def run_hooks_builtin(hooks_file: HooksFile) -> list[Finding]:
    # The built-in reads hooks only from `hooks/hooks.json` inside a plugin root, so both file
    # shapes go to it as a staged plugin that holds the hooks object. Its findings about the
    # staged manifest are about the staging, not the file, and are dropped.
    hooks_text = hooks_file.hooks_text_for_builtin()
    with tempfile.TemporaryDirectory() as staging:
        root = Path(staging)
        files = {
            root / '.claude-plugin' / 'plugin.json': '{"name": "staged"}',
            root / 'hooks' / 'hooks.json': hooks_text,
        }
        try:
            for path, text in files.items():
                path.parent.mkdir()
                path.write_text(text, encoding='utf-8')
        except OSError as problem:
            message = f'could not stage {hooks_file.path} for claude: {problem}'
            raise CannotCheckError(message) from problem
        return run_builtin(root, include_manifest=False)


def test_command(arguments: argparse.Namespace) -> int:
    """Return 0 for a pass, 1 for a contract failure, 2 when the hook could not be run."""
    hook_test = HookTest(
        script=arguments.script,
        payload=arguments.payload,
        expectations=Expectations(
            exit_code=arguments.expect_exit,
            fields=tuple(arguments.expect_field),
            silent=arguments.expect_silent,
        ),
        timeout=arguments.timeout,
        malformed=arguments.malformed,
    )
    try:
        findings = check_hook(hook_test)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    return report(f'{arguments.script.name} < {arguments.payload.name}', findings, strict=False)
