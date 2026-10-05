"""Failures while reading the project under review."""

from pathlib import Path

from python_harness.core.errors import PythonHarnessError


class ManifestUnreadableError(PythonHarnessError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f'{path} is not valid TOML: {reason}')
        self.path = path
        self.reason = reason
