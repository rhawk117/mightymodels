"""The checks every incoming review finding passes."""

from dataclasses import replace
from typing import TYPE_CHECKING, get_args

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
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
from mightymodels_core.vocabulary.reviews import FindingSeverity

from tests.core.reviews.finding_builders import fold_one, incoming_finding

if TYPE_CHECKING:
    from mightymodels_core.reviews import IncomingFinding
    from mightymodels_core.reviews.findings import FindingOptions


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


class TestFindingChecks:
    starts = st.integers(min_value=1, max_value=10_000)
    spans = starts.flatmap(
        lambda start: st.tuples(st.just(start), st.integers(min_value=start, max_value=10_000))
    )
    zero_start_spans = st.tuples(st.just(0), st.integers(min_value=0, max_value=10_000))
    zero_end_spans = st.tuples(starts, st.just(0))
    reversed_spans = starts.flatmap(
        lambda end: st.tuples(st.integers(min_value=end + 1, max_value=10_001), st.just(end))
    )

    def fold_location(self, location: str) -> None:
        fold_one([], incoming_finding(location=location))

    @pytest.fixture
    def refused_batch(self) -> list[IncomingFinding]:
        return [incoming_finding(), incoming_finding(location='src/q.py:0')]

    @given(span=zero_start_spans)
    @example(span=(0, 0))
    @example(span=(0, 3))
    def test_a_span_starting_at_zero_is_refused(self, span: tuple[int, int]) -> None:
        start, end = span
        with pytest.raises(LineBelowOneError):
            self.fold_location(f'src/q.py:{start}-{end}')

    @given(span=zero_end_spans)
    @example(span=(3, 0))
    def test_a_span_ending_at_zero_is_refused(self, span: tuple[int, int]) -> None:
        start, end = span
        with pytest.raises(LineBelowOneError):
            self.fold_location(f'src/q.py:{start}-{end}')

    @given(span=reversed_spans)
    @example(span=(9, 3))
    def test_a_reversed_span_is_refused(self, span: tuple[int, int]) -> None:
        start, end = span
        with pytest.raises(ReversedRangeError):
            self.fold_location(f'src/q.py:{start}-{end}')

    def test_a_single_line_below_one_is_refused(self) -> None:
        with pytest.raises(LineBelowOneError):
            self.fold_location('src/q.py:0')

    def test_a_location_without_a_line_is_refused(self) -> None:
        with pytest.raises(LocationShapeError):
            self.fold_location('nowhere')

    @given(line=starts)
    @example(line=1)
    def test_a_single_line_is_accepted_as_written(self, line: int) -> None:
        location = f'src/q.py:{line}'
        (stored,) = fold_one([], incoming_finding(location=location))

        assert stored.location == location

    @given(span=spans)
    @example(span=(3, 9))
    @example(span=(4, 4))
    def test_a_span_is_accepted_as_written(self, span: tuple[int, int]) -> None:
        start, end = span
        location = f'src/q.py:{start}-{end}'
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
    required_text_fields = st.sampled_from(['title', 'fix', 'verify', 'location'])

    @pytest.fixture
    def blank_evidence(self) -> IncomingEvidence:
        return IncomingEvidence(kind='metric', cite=' ')

    @pytest.fixture
    def tight_options(self) -> FindingOptions:
        return replace(ReviewOptions().findings, prose_limit=15)

    @pytest.fixture
    def short_secret(self) -> IncomingFinding:
        return incoming_finding(title='password=abcd')

    @given(field=required_text_fields)
    @example(field='title')
    @example(field='fix')
    @example(field='verify')
    @example(field='location')
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
    evidence_required_severities = st.sampled_from([
        severity for severity in get_args(FindingSeverity.__value__) if severity != 'Low'
    ])

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

    @given(severity=evidence_required_severities)
    @example(severity='Blocker')
    @example(severity='Critical')
    @example(severity='High')
    @example(severity='Medium')
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
