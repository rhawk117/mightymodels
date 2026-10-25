"""The errors of the crashout rules."""

from mightymodels_core.primitives import StateError


class BlankCrashoutFieldError(StateError):
    def __init__(self, *, field: str) -> None:
        self.field = field
        super().__init__(f'{field} is blank; say what happened')


class NoFailuresError(StateError):
    def __init__(self) -> None:
        super().__init__('a crashout names at least one failure')
