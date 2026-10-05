"""Failures mapping call sites reports as a message instead of a traceback."""

from python_harness.core.errors import PythonHarnessError


class UnknownTargetPathsError(PythonHarnessError):
    def __init__(self, paths: frozenset[str]) -> None:
        listed = ', '.join(sorted(paths))
        super().__init__(f'not discovered project modules: {listed}')
        self.paths = paths
