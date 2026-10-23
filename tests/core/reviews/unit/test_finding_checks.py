"""The checks every incoming review finding passes."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RedactedTextTooLongError, redact
from mightymodels_core.reviews import (
    FieldRequiredError,
    IncomingEvidence,
    LineBelowOneError,
    LocationShapeError,
    MalformedSourceError,
    ReversedRangeError,
    ReviewOptions,
    SourcesRequiredError,
    UnsupportedQualityError,
    fold_findings,
)

from tests.core.reviews.finding_builders import fold_one, incoming_finding

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.reviews import IncomingFinding
    from mightymodels_core.reviews.findings import FindingOptions
    from mightymodels_core.schemas.reviews import FindingSeverity


@dataclass(slots=True, kw_only=True, frozen=True)
class LocationCase:
    name: str
    location: str
    error_type: type[Exception]
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def bad_location_cases() -> pytest.MarkDecorator:
    cases = [
        LocationCase(name='line-zero', location='src/q.py:0', error_type=LineBelowOneError),
        LocationCase(name='range-from-zero', location='src/q.py:0-3', error_type=LineBelowOneError),
        LocationCase(name='range-to-zero', location='src/q.py:3-0', error_type=LineBelowOneError),
        LocationCase(name='reversed', location='src/q.py:9-3', error_type=ReversedRangeError),
        LocationCase(name='no-line', location='nowhere', error_type=LocationShapeError),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


def good_location_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('location', ['src/q.py:1', 'src/q.py:3-9', 'src/q.py:4-4'])


def blank_text_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('field', ['title', 'fix', 'verify', 'location'])


def sources_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('sources', 'error_type'),
        [
            pytest.param((), SourcesRequiredError, id='missing'),
            pytest.param(('XX-1',), MalformedSourceError, id='unknown-persona'),
            pytest.param(('UB-',), MalformedSourceError, id='no-number'),
            pytest.param(('UB-1', 'bad'), MalformedSourceError, id='one-bad-among-good'),
        ],
    )


def quality_severity_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('severity', ['Blocker', 'Critical', 'High', 'Medium'])


class TestFindingChecks:
    @pytest.fixture
    def refused_batch(self) -> list[IncomingFinding]:
        return [incoming_finding(), incoming_finding(location='src/q.py:0')]

    @bad_location_cases()
    def test_a_location_that_is_not_a_span_is_refused(self, case: LocationCase) -> None:
        with pytest.raises(case.error_type):
            fold_one([], incoming_finding(location=case.location))

    @good_location_cases()
    def test_a_span_is_accepted_as_written(self, location: str) -> None:
        (stored,) = fold_one([], incoming_finding(location=location))

        assert stored.location == location

    def test_the_refusal_names_the_finding_and_its_sources(
        self, refused_batch: list[IncomingFinding]
    ) -> None:
        with pytest.raises(LineBelowOneError) as raised:
            fold_findings([], refused_batch, ReviewOptions().findings)

        assert str(raised.value) == (
            'finding 1: location line 0 is below 1 (UB-1); nothing was written'
        )


class TestTextChecks:
    @pytest.fixture
    def blank_evidence(self) -> IncomingEvidence:
        return IncomingEvidence(kind='metric', cite=' ')

    @pytest.fixture
    def tight_options(self) -> FindingOptions:
        return replace(ReviewOptions().findings, prose_limit=15)

    @pytest.fixture
    def short_secret(self) -> IncomingFinding:
        return incoming_finding(title='password=abcd')

    @blank_text_cases()
    def test_blank_required_text_is_refused(self, field: str) -> None:
        with pytest.raises(FieldRequiredError) as raised:
            fold_one([], incoming_finding(**{field: '   '}))

        assert raised.value.field == field

    def test_a_blank_evidence_cite_is_refused(self, blank_evidence: IncomingEvidence) -> None:
        with pytest.raises(FieldRequiredError) as raised:
            fold_one([], incoming_finding(evidence=blank_evidence))

        assert raised.value.field == 'evidence cite'

    def test_text_that_redaction_lengthens_past_the_limit_is_refused(
        self, tight_options: FindingOptions, short_secret: IncomingFinding
    ) -> None:
        with pytest.raises(RedactedTextTooLongError):
            fold_findings([], [short_secret], tight_options)

    def test_text_is_stripped_and_redacted(self) -> None:
        (stored,) = fold_one([], incoming_finding(fix='  rotate password=abcd  '))

        assert stored.fix == redact('rotate password=abcd')
        assert 'abcd' not in stored.fix


class TestSourceAndQualityChecks:
    @pytest.fixture
    def cited(self) -> IncomingEvidence:
        return IncomingEvidence(kind='idiom', cite='  python.md rule  ')

    @pytest.fixture
    def misplaced_batch(self) -> list[IncomingFinding]:
        return [incoming_finding(), incoming_finding(location='nowhere')]

    @sources_cases()
    def test_missing_or_malformed_sources_are_refused(
        self, sources: tuple[str, ...], error_type: type[Exception]
    ) -> None:
        with pytest.raises(error_type):
            fold_one([], incoming_finding(sources=sources))

    def test_sources_are_sorted_and_deduplicated(self) -> None:
        (stored,) = fold_one([], incoming_finding(sources=('UB-2', 'MV-1', 'UB-2')))

        assert stored.sources == ('MV-1', 'UB-2')

    @quality_severity_cases()
    def test_quality_without_evidence_above_low_is_refused(self, severity: FindingSeverity) -> None:
        with pytest.raises(UnsupportedQualityError):
            fold_one([], incoming_finding(kind='quality', severity=severity))

    def test_quality_at_low_needs_no_evidence(self) -> None:
        (stored,) = fold_one([], incoming_finding(kind='quality', severity='Low'))

        assert stored.evidence is None

    def test_quality_with_evidence_is_stored_with_it(self, cited: IncomingEvidence) -> None:
        (stored,) = fold_one([], incoming_finding(kind='quality', evidence=cited))

        assert stored.evidence is not None
        assert stored.evidence.cite == redact('python.md rule')

    def test_a_refused_batch_places_nothing(self, misplaced_batch: list[IncomingFinding]) -> None:
        with pytest.raises(LocationShapeError):
            fold_findings([], misplaced_batch, ReviewOptions().findings)
