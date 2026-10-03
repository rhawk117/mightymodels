from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Finding:
    level: Literal['error', 'warning']
    message: str


def error(message: str) -> Finding:
    return Finding('error', message)


def warning(message: str) -> Finding:
    return Finding('warning', message)


def report(label: str, findings: list[Finding], *, strict: bool) -> int:
    """Print the findings and a verdict line; return 0, or 1 on an error or a strict warning."""
    errors = [finding for finding in findings if finding.level == 'error']
    warnings = [finding for finding in findings if finding.level == 'warning']
    for finding in findings:
        print(f'{finding.level}: {finding.message}')
    failed = bool(errors) or (strict and bool(warnings))
    verdict = 'FAIL' if failed else 'PASS'
    print(f'{verdict} {label}: {len(errors)} error(s), {len(warnings)} warning(s)')
    return 1 if failed else 0
