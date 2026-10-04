import argparse
import sys
import tempfile
from pathlib import Path

from vibe_code_cli.builtin import BuiltinRunner, Services
from vibe_code_cli.findings import CannotCheckError, Finding, report
from vibe_code_cli.mcp.checks import check_mcp
from vibe_code_cli.mcp.file import KINDS, SERVER_FILE_NAME, McpFile, load_mcp_file
from vibe_code_cli.mcp.help_probe import check_commands
from vibe_code_cli.mcp.scaffold.command import scaffold_command


def build(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser(
        'validate',
        help='run claude plugin validate on the servers, then the checks it misses',
    )
    validate.add_argument(
        'config_file',
        type=Path,
        metavar='FILE',
        help='plugin or project .mcp.json, or ~/.claude.json for user servers',
    )
    validate.add_argument(
        '--kind', choices=KINDS, required=True, help='where Claude Code loads the file from'
    )
    validate.add_argument(
        '--check-command',
        action='store_true',
        help='run COMMAND ARGS --help for each stdio server to prove it resolves',
    )
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)
    scaffold = commands.add_parser(
        'scaffold',
        help='render an MCP server project and its .mcp.json shapes from an interview spec',
    )
    scaffold.add_argument('spec', type=Path, metavar='SPEC', help='interview spec JSON')
    scaffold.add_argument('target', type=Path, metavar='TARGET', help='directory to write into')
    scaffold.add_argument(
        '--template',
        type=Path,
        metavar='DIR',
        help='project template (default: assets/template of the create-mcp skill)',
    )
    scaffold.add_argument(
        '--force', action='store_true', help='write into a non-empty TARGET, replacing its src/'
    )
    scaffold.set_defaults(handler=scaffold_command)


def dispatch(arguments: argparse.Namespace, services: Services) -> int:
    return int(arguments.handler(arguments, services))


def validate_command(arguments: argparse.Namespace, services: Services) -> int:
    path = arguments.config_file
    if not path.is_file():
        print(f'error: {path} is not a file', file=sys.stderr)
        return 2
    try:
        mcp_file = load_mcp_file(path, arguments.kind)
        findings = validate_findings(
            mcp_file, services.run_builtin, check_command=arguments.check_command
        )
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    return report(f'{path} as {arguments.kind}', findings, strict=arguments.strict)


def validate_findings(
    mcp_file: McpFile, runner: BuiltinRunner, *, check_command: bool
) -> list[Finding]:
    builtin_findings = run_mcp_builtin(mcp_file, runner)
    builtin_errored = any(finding.level == 'error' for finding in builtin_findings)
    own_findings = check_mcp(mcp_file, builtin_errored=builtin_errored)
    command_findings = check_commands(mcp_file) if check_command else []
    return [*builtin_findings, *own_findings, *command_findings]


def run_mcp_builtin(mcp_file: McpFile, runner: BuiltinRunner) -> list[Finding]:
    with tempfile.TemporaryDirectory() as staging:
        root = Path(staging)
        files = {
            root / '.claude-plugin' / 'plugin.json': '{"name": "staged"}',
            root / SERVER_FILE_NAME: mcp_file.builtin_text(),
        }
        try:
            (root / '.claude-plugin').mkdir()
            for path, text in files.items():
                path.write_text(text, encoding='utf-8')
        except OSError as problem:
            message = f'could not stage {mcp_file.path} for claude: {problem}'
            raise CannotCheckError(message) from problem
        return runner(root, include_manifest=False)
