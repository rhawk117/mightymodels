"""Argument combinations the commands refuse, reported as messages, not tracebacks."""

from pathlib import Path

from python_harness.core.errors import PythonistaError


class HeadWithoutDiffError(PythonistaError):
    def __init__(self, head: str) -> None:
        super().__init__(f'--head {head} needs --diff BASE')
        self.head = head


class FallbackRuffConfigMissingError(PythonistaError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'--fallback-ruff-config {path} is not a file')
        self.path = path
