import shutil
import subprocess
from pathlib import Path

import msgspec

from ai_engineer_cli.findings import CannotCheckError, Finding, error, warning


class BuiltinUnavailableError(CannotCheckError):
    """The built-in validator could not run, so no verdict exists."""


class ReportItem(msgspec.Struct):
    message: str
    path: str | None = None


class ReportSection(msgspec.Struct):
    errors: list[ReportItem] = []
    warnings: list[ReportItem] = []


class Report(msgspec.Struct):
    """The JSON that `claude plugin validate --json` prints; its other keys are not read."""

    manifest: ReportSection | None = None
    contents: list[ReportSection] = []


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
        report = msgspec.json.decode(stdout, type=Report)
    except msgspec.DecodeError as problem:
        message = f'claude plugin validate printed no JSON report: {problem}'
        raise BuiltinUnavailableError(message) from problem
    manifest = [report.manifest] if include_manifest and report.manifest is not None else []
    return [
        finding
        for section in [*manifest, *report.contents]
        for finding in section_findings(section)
    ]


def section_findings(section: ReportSection) -> list[Finding]:
    return [
        *(error(finding_text(item)) for item in section.errors),
        *(warning(finding_text(item)) for item in section.warnings),
    ]


def finding_text(item: ReportItem) -> str:
    if item.path:
        return f'{item.path}: {item.message}'
    return item.message
