"""The errors of the review repositories."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from mightymodels_core.primitives import RunId


class RunNotFoundError(StateError):
    def __init__(self, *, run: RunId) -> None:
        self.run = run
        super().__init__(f'no review run {run}; start one first')


class RunExistsError(StateError):
    def __init__(self, *, run: RunId) -> None:
        self.run = run
        super().__init__(f'review run {run} already exists')


class UnknownFindingError(StateError):
    def __init__(self, *, run: RunId, finding_key: str) -> None:
        self.run = run
        self.finding_key = finding_key
        super().__init__(f'review run {run} holds no finding {finding_key!r}')


class UndecidedFindingError(StateError):
    def __init__(self, *, run: RunId, finding_key: str) -> None:
        self.run = run
        self.finding_key = finding_key
        super().__init__(
            f'finding {finding_key!r} of review run {run} has no disposition; '
            'record a disposition before an outcome'
        )
