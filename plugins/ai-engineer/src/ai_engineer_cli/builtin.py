import json
import shutil
import subprocess
from pathlib import Path

from ai_engineer_cli.findings import CannotCheckError, Finding, error, warning


class BuiltinUnavailableError(CannotCheckError):
    """The built-in validator could not run, so no verdict exists."""


def run_builtin(target: Path, *, include_manifest: bool = True) -> list[Finding]:
    """Run `claude plugin validate --json` on target and return what it found.

    A caller that stages a throwaway manifest passes include_manifest=False to drop its findings.
    """
    claude = shutil.which('claude')
    if claude is None:
        message = 'claude is not on PATH: npm install -g @anthropic-ai/claude-code'
        raise BuiltinUnavailableError(message)
    result = subprocess.run(  # noqa: S603  # fixed argument list with no shell; target is a path
        [claude, 'plugin', 'validate', str(target), '--json'],
        capture_output=True,
        text=True,
        check=False,
    )
    findings = parse_report(result.stdout, include_manifest=include_manifest)
    if result.returncode != 0 and not any(finding.level == 'error' for finding in findings):
        message = f'claude plugin validate exited {result.returncode} with no error finding: '
        raise BuiltinUnavailableError(message + result.stderr.strip())
    return findings


def parse_report(stdout: str, *, include_manifest: bool = True) -> list[Finding]:
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as problem:
        message = f'claude plugin validate printed no JSON report: {problem}'
        raise BuiltinUnavailableError(message) from problem
    if not isinstance(report, dict):
        message = 'claude plugin validate printed a JSON report that is not an object'
        raise BuiltinUnavailableError(message)
    manifest = [report.get('manifest')] if include_manifest else []
    sections = [*manifest, *report.get('contents', [])]
    return [
        finding
        for section in sections
        if isinstance(section, dict)
        for finding in section_findings(section)
    ]


def section_findings(section: dict[str, list[dict[str, str]]]) -> list[Finding]:
    return [
        *(error(item['message']) for item in section.get('errors', [])),
        *(warning(item['message']) for item in section.get('warnings', [])),
    ]
