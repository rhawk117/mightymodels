"""What git answers with: the raw answer, the checkout it describes and the status filter."""

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING

from mightymodels_core.primitives import local_key, origin_key

from .errors import GitMissingError, GitNoAnswerError

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.primitives import RepositoryKey
    from mightymodels_core.process import FailureKind

    from .errors import GitUnanswered


class UntrackedFiles(StrEnum):
    NORMAL = auto()
    NO = auto()


@dataclass(slots=True, kw_only=True, frozen=True)
class GitAnswer:
    exit: int | None
    stdout: str
    stderr: str
    failure: FailureKind | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Checkout:
    toplevel: Path
    origin_url: str | None

    def repository_key(self) -> RepositoryKey:
        owner_and_name = None if self.origin_url is None else origin_key(self.origin_url)
        return local_key(self.toplevel) if owner_and_name is None else owner_and_name


def unanswered_error(answer: GitAnswer) -> GitUnanswered | None:
    if answer.failure is None:
        return None

    if answer.failure == 'not_found':
        return GitMissingError()

    return GitNoAnswerError(detail=answer.stderr)
