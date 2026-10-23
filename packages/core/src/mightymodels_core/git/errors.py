"""The errors of the git queries."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from pathlib import Path


class GitMissingError(StateError):
    def __init__(self) -> None:
        super().__init__('this needs git and no git executable is on PATH')


class GitNoAnswerError(StateError):
    def __init__(self, *, detail: str) -> None:
        self.detail = detail
        super().__init__(f'this needs git and git did not answer: {detail}')


class NotARepositoryError(StateError):
    def __init__(self, *, root: Path, detail: str) -> None:
        self.root = root
        self.detail = detail
        super().__init__(f'{root} is not inside a git repository: {detail}')


class UnsafeRevisionError(StateError):
    def __init__(self, *, revision: str) -> None:
        self.revision = revision
        super().__init__(f'{revision!r} is not a plain revision name')


class GitUnavailableError(StateError):
    def __init__(self, *, detail: str) -> None:
        self.detail = detail
        super().__init__(f'git could not list the commit changes: {detail}')


type GitUnanswered = GitMissingError | GitNoAnswerError
type GitRefusal = GitUnanswered | NotARepositoryError
