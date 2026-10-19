"""The errors of the review repositories."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import RunId
    from mightymodels_core.reviews.policy import Persona
    from mightymodels_core.schemas.reviews import Scope


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


class WeightsMissingError(StateError):
    def __init__(self) -> None:
        super().__init__('weights: custom emphasis needs weights')


class WeightRangeError(StateError):
    def __init__(self) -> None:
        super().__init__('weights: give both personas a weight between 0 and 1')


class WeightSumError(StateError):
    def __init__(self) -> None:
        super().__init__('weights: the weights must sum to 1')


class PersonaChoiceError(StateError):
    def __init__(self) -> None:
        super().__init__('quick depth runs one persona and the weights tie; pass persona')


class BaseRequiredError(StateError):
    def __init__(self, *, scope: Scope) -> None:
        self.scope = scope
        super().__init__(f'{scope} scope needs base, the ref it is reviewed against')


class SlugRequiredError(StateError):
    def __init__(self) -> None:
        super().__init__('ticket scope needs slug')


class OverrideSpentError(StateError):
    def __init__(self, *, run: RunId) -> None:
        self.run = run
        super().__init__(f'review run {run} has used its one reviewer override')


def report_refusal(problem: str) -> str:
    return f'report: {problem}; nothing was written'


class NoFindingsSectionError(StateError):
    def __init__(self) -> None:
        super().__init__(report_refusal('there is no "## Findings" section'))


class UnknownSeverityHeadingError(StateError):
    def __init__(self, *, heading: str) -> None:
        self.heading = heading
        super().__init__(report_refusal(f'{heading!r} is not a severity heading'))


class UnreadableHeadingError(StateError):
    def __init__(self, *, heading: str) -> None:
        self.heading = heading
        super().__init__(report_refusal(f'{heading!r} is not a finding heading'))


class UnplacedFindingError(StateError):
    def __init__(self, *, heading: str) -> None:
        self.heading = heading
        super().__init__(report_refusal(f'{heading!r} comes before any severity heading'))


class ForeignSourceError(StateError):
    def __init__(self, *, index: int, sources: Sequence[str], persona: Persona) -> None:
        self.index = index
        self.sources = tuple(sources)
        self.persona = persona
        super().__init__(
            finding_refusal(index, f'a {persona} report holds only its own finding ids', sources)
        )


class EvidenceKindError(StateError):
    def __init__(self, *, index: int, sources: Sequence[str], kind: str) -> None:
        self.index = index
        self.sources = tuple(sources)
        self.kind = kind
        super().__init__(
            finding_refusal(
                index, f'evidence kind {kind!r} is not metric, idiom or convention', sources
            )
        )


class UnknownDimensionError(StateError):
    def __init__(self, *, index: int, sources: Sequence[str], dimension: str) -> None:
        self.index = index
        self.sources = tuple(sources)
        self.dimension = dimension
        super().__init__(
            finding_refusal(
                index,
                f'dimension {dimension!r} is not security, sdlc, quality, docs or plan',
                sources,
            )
        )
