"""Failures that stop the gate before any verification tool starts."""

from python_harness.core.errors import PythonHarnessError


class LauncherUnavailableError(PythonHarnessError):
    def __init__(self, program: str) -> None:
        super().__init__(f'{program} is not on PATH; the gate launches its tools with it')
        self.program = program
