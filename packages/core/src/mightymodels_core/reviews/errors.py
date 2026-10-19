"""The errors of the review repositories."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from collections.abc import Sequence

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


def finding_refusal(index: int, problem: str, sources: Sequence[str] = ()) -> str:
    return f'finding {index}: {problem} ({"/".join(sources)}); nothing was written'


class SourcesRequiredError(StateError):
    def __init__(self, *, index: int) -> None:
        self.index = index
        super().__init__(finding_refusal(index, 'at least one source is required'))


class MalformedSourceError(StateError):
    def __init__(self, *, index: int, source: str) -> None:
        self.index = index
        self.source = source
        super().__init__(finding_refusal(index, f'source {source!r} must look like MV-1 or UB-1'))


class FieldRequiredError(StateError):
    def __init__(self, *, index: int, sources: Sequence[str], field: str) -> None:
        self.index = index
        self.sources = tuple(sources)
        self.field = field
        super().__init__(finding_refusal(index, f'{field} is required', sources))


class LocationShapeError(StateError):
    def __init__(self, *, index: int, sources: Sequence[str]) -> None:
        self.index = index
        self.sources = tuple(sources)
        super().__init__(
            finding_refusal(index, 'location must be path:line or path:start-end', sources)
        )


class LineBelowOneError(StateError):
    def __init__(self, *, index: int, sources: Sequence[str], line: int) -> None:
        self.index = index
        self.sources = tuple(sources)
        self.line = line
        super().__init__(finding_refusal(index, f'location line {line} is below 1', sources))


class ReversedRangeError(StateError):
    def __init__(self, *, index: int, sources: Sequence[str], lines: tuple[int, int]) -> None:
        self.index = index
        self.sources = tuple(sources)
        self.start, self.end = lines
        super().__init__(
            finding_refusal(
                index, f'location range {lines[0]}-{lines[1]} ends before it starts', sources
            )
        )


class UnsupportedQualityError(StateError):
    def __init__(self, *, index: int, sources: Sequence[str]) -> None:
        self.index = index
        self.sources = tuple(sources)
        super().__init__(
            finding_refusal(
                index,
                'a quality finding at Medium or above needs structured evidence '
                '(metric, idiom, or convention); lower it to Low or cite the evidence',
                sources,
            )
        )
