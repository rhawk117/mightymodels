"""The refusals of the review signals domain, each a `SignalsError`."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from pathlib import Path


class SignalsError(StateError):
    pass


class NoRepositoryError(SignalsError):
    def __init__(self, *, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


class TargetOutsideError(SignalsError):
    def __init__(self, *, target: str) -> None:
        super().__init__(f'--target {target!r} is outside the repository')


class TargetNotUnicodeError(SignalsError):
    def __init__(self, *, path: str) -> None:
        super().__init__(f'--target resolves to {path!r}, which is not valid Unicode')


class GitMissingError(SignalsError):
    def __init__(self) -> None:
        super().__init__('git is not on PATH')


class GitFailedError(SignalsError):
    def __init__(self, *, detail: str) -> None:
        super().__init__(f'git log failed: {detail}')
