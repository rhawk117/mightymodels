import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from vibe_code_cli.builtin import run_builtin
from vibe_code_cli.findings import CannotCheckError, Finding, error, report
from vibe_code_cli.frontmatter import parse_skill_text
from vibe_code_cli.skill.body import check_body
from vibe_code_cli.skill.fields import check_fields, directory_name_of


def build_group(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    validate = commands.add_parser(
        'validate',
        help='run claude plugin validate, then the checks it misses',
    )
    validate.add_argument('skill_dir', type=Path, metavar='SKILL_DIR', help='skill directory')
    validate.add_argument('--strict', action='store_true', help='exit 1 on warnings too')
    validate.set_defaults(handler=validate_command)


def validate_command(arguments: argparse.Namespace) -> int:
    """Return 0 for a pass, 1 for findings, 2 when the check could not run."""
    skill_dir = arguments.skill_dir
    if not skill_dir.is_dir():
        print(f'error: {skill_dir} is not a directory', file=sys.stderr)
        return 2
    try:
        builtin_findings = run_skill_builtin(skill_dir)
        builtin_errored = any(finding.level == 'error' for finding in builtin_findings)
        own_findings = check_skill(skill_dir, builtin_errored=builtin_errored)
    except CannotCheckError as problem:
        print(f'error: {problem}', file=sys.stderr)
        return 2
    findings = [*builtin_findings, *own_findings]
    return report(directory_name_of(skill_dir), findings, strict=arguments.strict)


def run_skill_builtin(skill_dir: Path) -> list[Finding]:
    # The built-in reads skills only from a directory named `skills` (or a plugin root), and
    # would also report on siblings, so it gets a copy of this one skill alone under `skills`.
    with tempfile.TemporaryDirectory() as staging:
        skills = Path(staging) / 'skills'
        try:
            shutil.copytree(skill_dir, skills / directory_name_of(skill_dir), symlinks=True)
        except (shutil.Error, OSError) as problem:
            message = f'could not read {skill_dir} to hand it to claude: {problem}'
            raise CannotCheckError(message) from problem
        return run_builtin(skills)


def check_skill(skill_dir: Path, *, builtin_errored: bool = False) -> list[Finding]:
    """The checks `claude plugin validate` is silent on.

    Raises CannotCheckError when the frontmatter is invalid YAML that the built-in let pass.
    """
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.is_file():
        return [error(f'{skill_md} not found')]
    try:
        text = skill_md.read_text(encoding='utf-8')
    except OSError:
        return []  # the built-in reports an unreadable SKILL.md
    except UnicodeError:
        return [error(f'{skill_md} is not valid UTF-8')]
    skill = parse_skill_text(text)
    if skill.yaml_problem is not None and not builtin_errored:
        message = (
            f'{skill_md}: frontmatter is not valid YAML ({skill.yaml_problem}); '
            'the field checks could not run'
        )
        raise CannotCheckError(message)
    findings = [error(problem) for problem in skill.key_problems]
    if skill.fields is not None:
        findings.extend(
            check_fields(
                skill.fields, directory_name_of(skill_dir), builtin_errored=builtin_errored
            )
        )
    findings.extend(check_body(skill_dir, text, skill.body))
    return findings
