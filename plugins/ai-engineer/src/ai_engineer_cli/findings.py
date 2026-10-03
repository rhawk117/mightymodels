from dataclasses import dataclass
from typing import Literal


class CannotCheckError(Exception):
    """The skill cannot be fully checked, so the command must give no verdict."""


@dataclass(frozen=True)
class Finding:
    level: Literal['error', 'warning', 'info']
    message: str


def error(message: str) -> Finding:
    return Finding('error', message)


def warning(message: str) -> Finding:
    return Finding('warning', message)


def info(message: str) -> Finding:
    return Finding('info', message)


def report(label: str, findings: list[Finding], *, strict: bool) -> int:
    """Print the findings and a verdict line; return 0, or 1 on an error or a strict warning.

    An info finding is printed and counted but never changes the verdict.
    """
    errors = [finding for finding in findings if finding.level == 'error']
    warnings = [finding for finding in findings if finding.level == 'warning']
    infos = [finding for finding in findings if finding.level == 'info']
    for finding in findings:
        print(f'{finding.level}: {finding.message}')
    failed = bool(errors) or (strict and bool(warnings))
    verdict = 'FAIL' if failed else 'PASS'
    counts = f'{len(errors)} error(s), {len(warnings)} warning(s)'
    if infos:
        counts += f', {len(infos)} info'
    print(f'{verdict} {label}: {counts}')
    return 1 if failed else 0
