"""How an incoming review finding merges into the held findings."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import redact
from mightymodels_core.reviews import (
    IncomingEvidence,
    ReviewOptions,
    fold_findings,
    stored_severity,
)
from mightymodels_core.reviews.findings import finding_number
from mightymodels_core.reviews.policy.review import (
    persona_of_source,
)

from .finding_builders import fold_one, held_finding, incoming_finding

if TYPE_CHECKING:
    from mightymodels_core.reviews import (
        FindingRecord,
        IncomingFinding,
    )
    from mightymodels_core.reviews.findings import FindingOptions


def finding_key_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(('key', 'number'), [('F1', 1), ('F12', 12)])


def source_persona_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('source', 'persona'), [('MV-3', 'merge-vader'), ('UB-16', 'uncle-bob')]
    )


class TestStoredSeverity:
    @pytest.fixture
    def options(self) -> FindingOptions:
        return ReviewOptions().findings

    def test_a_blocker_ranks_without_raising(self, options: FindingOptions) -> None:
        assert options.rank(stored_severity('Blocker')) == options.rank('High')


class TestFindingNumbering:
    def test_a_blocker_is_stored_as_high(self) -> None:
        (stored,) = fold_one([], incoming_finding(severity='Blocker'))

        assert stored.severity == 'High'

    def test_the_first_finding_takes_the_first_key(self) -> None:
        (stored,) = fold_one([], incoming_finding())

        assert stored.key == 'F1'


class TestKeyParsing:
    @finding_key_cases()
    def test_finding_number_reads_the_digits(self, key: str, number: int) -> None:
        assert finding_number(key) == number

    @source_persona_cases()
    def test_persona_of_source_reads_the_prefix(self, source: str, persona: str) -> None:
        assert persona_of_source(source, ReviewOptions().source_personas) == persona


class TestFindingOverlap:
    @pytest.fixture
    def spread_held(self) -> list[FindingRecord]:
        return [held_finding('F2'), held_finding('F7', location=redact('src/other.py:1'))]

    @pytest.fixture
    def held_one(self) -> list[FindingRecord]:
        return [held_finding('F1')]

    def test_no_overlap_takes_the_next_key(self, spread_held: list[FindingRecord]) -> None:
        (stored,) = fold_one(spread_held, incoming_finding(location='src/z.py:1'))

        assert stored.key == 'F8'

    def test_overlap_on_one_file_merges_and_joins_sources(
        self, held_one: list[FindingRecord]
    ) -> None:
        (stored,) = fold_one(held_one, incoming_finding(location='src/q.py:20-30'))

        assert (stored.key, stored.sources) == ('F1', ('MV-1', 'UB-1'))

    def test_the_same_lines_on_another_file_do_not_merge(
        self, held_one: list[FindingRecord]
    ) -> None:
        (stored,) = fold_one(held_one, incoming_finding(location='src/r.py:10-20'))

        assert stored.key == 'F2'

    def test_disjoint_ranges_do_not_merge(self, held_one: list[FindingRecord]) -> None:
        (stored,) = fold_one(held_one, incoming_finding(location='src/q.py:21-30'))

        assert stored.key == 'F2'


class TestFindingMerge:
    @pytest.fixture
    def held_medium(self) -> list[FindingRecord]:
        return [held_finding('F1', severity='Medium')]

    @pytest.fixture
    def held_critical(self) -> list[FindingRecord]:
        return [held_finding('F1', severity='Critical')]

    @pytest.fixture
    def held_security(self) -> list[FindingRecord]:
        return [held_finding('F1', security=True)]

    @pytest.fixture
    def cited(self) -> IncomingEvidence:
        return IncomingEvidence(kind='metric', cite='coupling 9')

    def test_the_higher_severity_side_wins_its_fields(
        self, held_medium: list[FindingRecord]
    ) -> None:
        (stored,) = fold_one(held_medium, incoming_finding(severity='High', title='Incoming title'))

        assert (stored.severity, stored.title) == ('High', redact('Incoming title'))
        assert stored.conflict is None

    def test_the_held_side_wins_when_it_is_higher(self, held_critical: list[FindingRecord]) -> None:
        (stored,) = fold_one(
            held_critical, incoming_finding(severity='High', title='Incoming title')
        )

        assert (stored.severity, stored.title) == ('Critical', redact('Held title'))
        assert stored.conflict is None

    def test_security_is_either_sides(self, held_security: list[FindingRecord]) -> None:
        (stored,) = fold_one(held_security, incoming_finding(security=False))

        assert stored.security is True

    def test_evidence_falls_back_to_the_other_side(
        self, held_medium: list[FindingRecord], cited: IncomingEvidence
    ) -> None:
        (stored,) = fold_one(
            held_medium, incoming_finding(severity='High', kind='quality', evidence=cited)
        )
        (kept,) = fold_one([replace(stored, severity='Medium')], incoming_finding(severity='High'))

        assert stored.evidence is not None
        assert kept.evidence == stored.evidence


class TestFindingConflict:
    earlier = redact('earlier conflict')

    @pytest.fixture
    def held_low(self) -> list[FindingRecord]:
        return [held_finding('F1', severity='Low')]

    @pytest.fixture
    def held_conflicted(self) -> list[FindingRecord]:
        return [held_finding('F1', severity='Medium', conflict=self.earlier)]

    def test_a_gap_of_two_records_a_conflict(self, held_low: list[FindingRecord]) -> None:
        (stored,) = fold_one(held_low, incoming_finding(severity='High'))

        assert stored.conflict == redact('MV-1 rated Low, UB-1 rated High: the user decides')

    def test_a_gap_of_one_keeps_the_earlier_conflict(
        self, held_conflicted: list[FindingRecord]
    ) -> None:
        (stored,) = fold_one(held_conflicted, incoming_finding(severity='High'))

        assert stored.conflict == self.earlier


class TestFindingBatch:
    @pytest.fixture
    def held_unparsable(self) -> list[FindingRecord]:
        return [held_finding('F1', location=redact('nowhere'))]

    @pytest.fixture
    def held_pair(self) -> list[FindingRecord]:
        return [held_finding('F1'), held_finding('F2', location=redact('src/a.py:1'))]

    @pytest.fixture
    def touching_batch(self) -> list[IncomingFinding]:
        first = incoming_finding(sources=('UB-1',), location='src/q.py:1-5')
        second = incoming_finding(sources=('UB-2',), location='src/q.py:5-9')
        return [first, second]

    @pytest.fixture
    def mixed_batch(self) -> list[IncomingFinding]:
        return [
            incoming_finding(location='src/new.py:1'),
            incoming_finding(location='src/a.py:1', sources=('UB-3',)),
        ]

    def test_an_unparsable_stored_location_overlaps_nothing(
        self, held_unparsable: list[FindingRecord]
    ) -> None:
        (stored,) = fold_one(held_unparsable, incoming_finding())

        assert stored.key == 'F2'

    def test_later_findings_in_a_batch_see_earlier_ones(
        self, touching_batch: list[IncomingFinding]
    ) -> None:
        (stored,) = fold_findings([], touching_batch, ReviewOptions().findings)

        assert (stored.key, stored.sources) == ('F1', ('UB-1', 'UB-2'))

    def test_only_changed_findings_return_in_key_order(
        self, held_pair: list[FindingRecord], mixed_batch: list[IncomingFinding]
    ) -> None:
        stored = fold_findings(held_pair, mixed_batch, ReviewOptions().findings)

        assert [finding.key for finding in stored] == ['F2', 'F3']
