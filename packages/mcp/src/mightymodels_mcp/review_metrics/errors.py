"""The refusals of the review metrics domain, each a `StateError`."""

from mightymodels_core.primitives import StateError


class MetricsWriteError(StateError):
    def __init__(self, *, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f'could not write {path}: {reason}')
