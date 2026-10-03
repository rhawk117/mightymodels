import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from ai_engineer_cli.agent_body import check_body
from ai_engineer_cli.agent_fields import check_fields
from ai_engineer_cli.agent_text import parse_agent_text
from ai_engineer_cli.builtin import run_builtin
from ai_engineer_cli.findings import CannotCheckError, Finding, error, report

NO_FRONTMATTER_BLOCK = (
    'no frontmatter block: the file must start with a --- line and close the block with '
    'another --- line, or Claude Code treats it as documentation and does not load it'
)


def build_group(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser(
        'validate',
        help='run claude plugin validate on an agent file, then the checks it misses',
    )
    validate.add_argument('agent_file', type=Path, metavar='FILE', help='agent .md file')
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)


def validate_command(arguments: argparse.Namespace) -> int:
    """Return 0 for a pass, 1 for findings, 2 when the check could not run."""
    path = arguments.agent_file
    try:
        text = read_agent_file(path)
        findings = validate_findings(path, text)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    return report(path.name, findings, strict=arguments.strict)


def read_agent_file(path: Path) -> str:
    if path.suffix != '.md' or not path.is_file():
        message = f'{path} is not a .md file'
        raise CannotCheckError(message)
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as problem:
        message = f'could not read {path}: {problem}'
        raise CannotCheckError(message) from problem


def is_plugin_agent(path: Path) -> bool:
    """A file in an `agents/` directory is a plugin agent unless it is under `.claude/`."""
    directory = path.resolve().parent
    return directory.name == 'agents' and directory.parent.name != '.claude'


def validate_findings(path: Path, text: str) -> list[Finding]:
    plugin = is_plugin_agent(path)
    builtin_findings = run_agent_builtin(path, plugin=plugin)
    builtin_errored = any(finding.level == 'error' for finding in builtin_findings)
    own_findings = check_agent(text, plugin=plugin, builtin_errored=builtin_errored)
    return [*builtin_findings, *own_findings]


def run_agent_builtin(path: Path, *, plugin: bool) -> list[Finding]:
    # The built-in answers differently for the two shapes and would also report on siblings,
    # so it gets a copy of this one file in the shape it sits in. Its findings about the staged
    # manifest are about the staging, not the file, and are dropped.
    with tempfile.TemporaryDirectory() as staging:
        root = Path(staging)
        try:
            target = stage_agent(path, root, plugin=plugin)
        except OSError as problem:
            message = f'could not stage {path} for claude: {problem}'
            raise CannotCheckError(message) from problem
        return run_builtin(target, include_manifest=False)


def stage_agent(path: Path, root: Path, *, plugin: bool) -> Path:
    """Copy the file under root; return the directory to hand to the built-in."""
    if plugin:
        manifest = root / '.claude-plugin' / 'plugin.json'
        manifest.parent.mkdir()
        manifest.write_text('{"name": "staged"}', encoding='utf-8')
        agents = root / 'agents'
        target = root
    else:
        agents = root / '.claude' / 'agents'
        target = agents
    agents.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, agents / path.name)
    return target


def check_agent(text: str, *, plugin: bool, builtin_errored: bool) -> list[Finding]:
    """The checks `claude plugin validate` is silent on.

    Raises CannotCheckError when the frontmatter is invalid YAML that the built-in let pass.
    """
    agent = parse_agent_text(text)
    if not agent.has_block:
        # The built-in warns about a plugin agent with no block; in `.claude/agents/` it is silent.
        return [] if plugin else [error(NO_FRONTMATTER_BLOCK)]
    if agent.yaml_problem is not None and not builtin_errored:
        message = (
            f'frontmatter is not valid YAML ({agent.yaml_problem}); the field checks could not run'
        )
        raise CannotCheckError(message)
    findings: list[Finding] = []
    if agent.fields is not None:
        findings.extend(
            check_fields(agent.fields, plugin=plugin, unquoted_colon=agent.unquoted_colon)
        )
    return [*findings, *check_body(agent.body)]
