"""The checks every incoming review finding passes and the merge into the held findings."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RedactedTextTooLongError, redact
from mightymodels_core.reviews import (
    FieldRequiredError,
    FindingRecord,
    IncomingEvidence,
    IncomingFinding,
    LineBelowOneError,
    LocationShapeError,
    MalformedSourceError,
    ReversedRangeError,
    SourcesRequiredError,
    UnsupportedQualityError,
    fold_findings,
    stored_severity,
)
from mightymodels_core.reviews.findings import finding_number
from mightymodels_core.reviews.policy.review import (
    create_finding_options,
    create_source_personas,
    persona_of_source,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.schemas.reviews import FindingSeverity


def incoming_finding(**changes: object) -> IncomingFinding:
    finding = IncomingFinding(
        sources=('UB-1',),
        severity='High',
        kind='defect',
        security=False,
        title='Unchecked input',
        location='src/q.py:10-20',
        fix='Check it',
        verify='Run the tests',
        evidence=None,
    )
    return replace(finding, **changes)


def held_finding(key: str, **changes: object) -> FindingRecord:
    record = FindingRecord(
        key=key,
        sources=('MV-1',),
        severity='High',
        kind='defect',
        security=False,
        title=redact('Held title'),
        location=redact('src/q.py:10-20'),
        fix=redact('Held fix'),
        verify=redact('Held verify'),
        evidence=None,
        conflict=None,
    )
    return replace(record, **changes)


@dataclass(slots=True, kw_only=True, frozen=True)
class LocationCase:
    name: str
    location: str
    error_type: type[Exception]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


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


def fold_one(held: list[FindingRecord], finding: IncomingFinding) -> list[FindingRecord]:
    return fold_findings(held, [finding], create_finding_options())


class TestFindingChecks:
    @bad_location_cases()
    def test_a_location_that_is_not_a_span_is_refused(self, case: LocationCase) -> None:
        with pytest.raises(case.error_type):
            fold_one([], incoming_finding(location=case.location))

    @good_location_cases()
    def test_a_span_is_accepted_as_written(self, location: str) -> None:
        (stored,) = fold_one([], incoming_finding(location=location))

        assert stored.location == location

    def test_the_refusal_names_the_finding_and_its_sources(self) -> None:
        with pytest.raises(LineBelowOneError) as raised:
            fold_findings(
                [],
                [incoming_finding(), incoming_finding(location='src/q.py:0')],
                create_finding_options(),
            )

        assert str(raised.value) == (
            'finding 1: location line 0 is below 1 (UB-1); nothing was written'
        )


class TestTextChecks:
    @blank_text_cases()
    def test_blank_required_text_is_refused(self, field: str) -> None:
        with pytest.raises(FieldRequiredError) as raised:
            fold_one([], incoming_finding(**{field: '   '}))

        assert raised.value.field == field

    def test_a_blank_evidence_cite_is_refused(self) -> None:
        blank = IncomingEvidence(kind='metric', cite=' ')

        with pytest.raises(FieldRequiredError) as raised:
            fold_one([], incoming_finding(evidence=blank))

        assert raised.value.field == 'evidence cite'

    def test_text_that_redaction_lengthens_past_the_limit_is_refused(self) -> None:
        options = replace(create_finding_options(), prose_limit=15)
        short_secret = incoming_finding(title='password=abcd')

        with pytest.raises(RedactedTextTooLongError):
            fold_findings([], [short_secret], options)

    def test_text_is_stripped_and_redacted(self) -> None:
        (stored,) = fold_one([], incoming_finding(fix='  rotate password=abcd  '))

        assert stored.fix == redact('rotate password=abcd')
        assert 'abcd' not in stored.fix


class TestSourceAndQualityChecks:
    @sources_cases()
    def test_missing_or_malformed_sources_are_refused(
        self, sources: tuple[str, ...], error_type: type[Exception]
    ) -> None:
        with pytest.raises(error_type):
            fold_one([], incoming_finding(sources=sources))

    def test_sources_are_sorted_and_deduplicated(self) -> None:
        (stored,) = fold_one([], incoming_finding(sources=('UB-2', 'MV-1', 'UB-2')))

        assert stored.sources == ('MV-1', 'UB-2')

    @pytest.mark.parametrize('severity', ['Blocker', 'Critical', 'High', 'Medium'])
    def test_quality_without_evidence_above_low_is_refused(self, severity: FindingSeverity) -> None:
        with pytest.raises(UnsupportedQualityError):
            fold_one([], incoming_finding(kind='quality', severity=severity))

    def test_quality_at_low_needs_no_evidence(self) -> None:
        (stored,) = fold_one([], incoming_finding(kind='quality', severity='Low'))

        assert stored.evidence is None

    def test_quality_with_evidence_is_stored_with_it(self) -> None:
        cited = IncomingEvidence(kind='idiom', cite='  python.md rule  ')

        (stored,) = fold_one([], incoming_finding(kind='quality', evidence=cited))

        assert stored.evidence is not None
        assert stored.evidence.cite == redact('python.md rule')

    def test_a_refused_batch_places_nothing(self) -> None:
        with pytest.raises(LocationShapeError):
            fold_findings(
                [],
                [incoming_finding(), incoming_finding(location='nowhere')],
                create_finding_options(),
            )


class TestStoredSeverity:
    def test_a_blocker_ranks_without_raising(self) -> None:
        options = create_finding_options()
        assert options.rank(stored_severity('Blocker')) == options.rank('High')


class TestFindingNumbering:
    def test_a_blocker_is_stored_as_high(self) -> None:
        (stored,) = fold_one([], incoming_finding(severity='Blocker'))

        assert stored.severity == 'High'

    def test_the_first_finding_takes_the_first_key(self) -> None:
        (stored,) = fold_one([], incoming_finding())

        assert stored.key == 'F1'


class TestKeyParsing:
    @pytest.mark.parametrize(('key', 'number'), [('F1', 1), ('F12', 12)])
    def test_finding_number_reads_the_digits(self, key: str, number: int) -> None:
        assert finding_number(key) == number

    @pytest.mark.parametrize(
        ('source', 'persona'), [('MV-3', 'merge-vader'), ('UB-16', 'uncle-bob')]
    )
    def test_persona_of_source_reads_the_prefix(self, source: str, persona: str) -> None:
        assert persona_of_source(source, create_source_personas()) == persona


class TestFindingOverlap:
    def test_no_overlap_takes_the_next_key(self) -> None:
        held = [held_finding('F2'), held_finding('F7', location=redact('src/other.py:1'))]

        (stored,) = fold_one(held, incoming_finding(location='src/z.py:1'))

        assert stored.key == 'F8'

    def test_overlap_on_one_file_merges_and_joins_sources(self) -> None:
        held = [held_finding('F1')]

        (stored,) = fold_one(held, incoming_finding(location='src/q.py:20-30'))

        assert (stored.key, stored.sources) == ('F1', ('MV-1', 'UB-1'))

    def test_the_same_lines_on_another_file_do_not_merge(self) -> None:
        (stored,) = fold_one([held_finding('F1')], incoming_finding(location='src/r.py:10-20'))

        assert stored.key == 'F2'

    def test_disjoint_ranges_do_not_merge(self) -> None:
        (stored,) = fold_one([held_finding('F1')], incoming_finding(location='src/q.py:21-30'))

        assert stored.key == 'F2'


class TestFindingMerge:
    def test_the_higher_severity_side_wins_its_fields(self) -> None:
        held = [held_finding('F1', severity='Medium')]

        (stored,) = fold_one(held, incoming_finding(severity='High', title='Incoming title'))

        assert (stored.severity, stored.title) == ('High', redact('Incoming title'))
        assert stored.conflict is None

    def test_the_held_side_wins_when_it_is_higher(self) -> None:
        held = [held_finding('F1', severity='Critical')]

        (stored,) = fold_one(held, incoming_finding(severity='High', title='Incoming title'))

        assert (stored.severity, stored.title) == ('Critical', redact('Held title'))
        assert stored.conflict is None

    def test_security_is_either_sides(self) -> None:
        held = [held_finding('F1', security=True)]

        (stored,) = fold_one(held, incoming_finding(security=False))

        assert stored.security is True

    def test_evidence_falls_back_to_the_other_side(self) -> None:
        cited = IncomingEvidence(kind='metric', cite='coupling 9')
        held = [held_finding('F1', severity='Medium')]

        (stored,) = fold_one(
            held, incoming_finding(severity='High', kind='quality', evidence=cited)
        )
        (kept,) = fold_one([replace(stored, severity='Medium')], incoming_finding(severity='High'))

        assert stored.evidence is not None
        assert kept.evidence == stored.evidence

    def test_a_gap_of_two_records_a_conflict(self) -> None:
        held = [held_finding('F1', severity='Low')]

        (stored,) = fold_one(held, incoming_finding(severity='High'))

        assert stored.conflict == redact('MV-1 rated Low, UB-1 rated High: the user decides')

    def test_a_gap_of_one_keeps_the_earlier_conflict(self) -> None:
        earlier = redact('earlier conflict')
        held = [held_finding('F1', severity='Medium', conflict=earlier)]

        (stored,) = fold_one(held, incoming_finding(severity='High'))

        assert stored.conflict == earlier

    def test_an_unparsable_stored_location_overlaps_nothing(self) -> None:
        held = [held_finding('F1', location=redact('nowhere'))]

        (stored,) = fold_one(held, incoming_finding())

        assert stored.key == 'F2'

    def test_later_findings_in_a_batch_see_earlier_ones(self) -> None:
        first = incoming_finding(sources=('UB-1',), location='src/q.py:1-5')
        second = incoming_finding(sources=('UB-2',), location='src/q.py:5-9')

        (stored,) = fold_findings([], [first, second], create_finding_options())

        assert (stored.key, stored.sources) == ('F1', ('UB-1', 'UB-2'))

    def test_only_changed_findings_return_in_key_order(self) -> None:
        held = [held_finding('F1'), held_finding('F2', location=redact('src/a.py:1'))]
        batch = [
            incoming_finding(location='src/new.py:1'),
            incoming_finding(location='src/a.py:1', sources=('UB-3',)),
        ]

        stored = fold_findings(held, batch, create_finding_options())

        assert [finding.key for finding in stored] == ['F2', 'F3']
