"""The similarity repository contract, written once for every tier to subclass."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.similarity import CANDIDATE_CAP, MATCH_OVERLAP, SimilarityRepository

from tests.core.similarity.similarity_builders import (
    STORED_REFERENCE,
    STORED_TEXT,
    create_written,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.similarity import Written

    from tests.core.similarity.similarity_builders import SimilarityHarness

NEAR_TEXT = 'retry loop drops connection pool after timeout error'
SHARES_ONE_WORD_TEXT = 'a timeout in the payment webhook handler'
UNRELATED_TEXT = 'rename the settings key in the helm chart'


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordCase:
    name: str
    text: str
    duplicates_stored: bool

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def similarity_record_cases() -> pytest.MarkDecorator:
    near = RecordCase(name='near-copy', text=NEAR_TEXT, duplicates_stored=True)
    one_word = RecordCase(
        name='one-shared-word', text=SHARES_ONE_WORD_TEXT, duplicates_stored=False
    )
    unrelated = RecordCase(name='unrelated', text=UNRELATED_TEXT, duplicates_stored=False)
    stop_words = RecordCase(name='common-words-only', text='the and of', duplicates_stored=False)
    return pytest.mark.parametrize(
        'case', [near.param, one_word.param, unrelated.param, stop_words.param]
    )


class SimilarityRepositoryContract:
    class TestImplementations:
        def test_repository_satisfies_the_protocol(self, harness: SimilarityHarness) -> None:
            assert isinstance(harness.similarity, SimilarityRepository)

    class TestSearch:
        def test_empty_repository_finds_nothing(self, harness: SimilarityHarness) -> None:
            assert harness.similarity.search(STORED_TEXT, kind=None) == []

        def test_stored_text_is_found_with_its_overlap(self, stocked: SimilarityHarness) -> None:
            found = stocked.similarity.search(NEAR_TEXT, kind=None)

            assert [(match.reference, match.overlap > MATCH_OVERLAP) for match in found] == [
                (STORED_REFERENCE, True)
            ]

        def test_query_of_common_words_finds_nothing(self, stocked: SimilarityHarness) -> None:
            assert stocked.similarity.search('the and of', kind=None) == []

        def test_query_with_search_syntax_is_a_plain_query(
            self, stocked: SimilarityHarness
        ) -> None:
            found = stocked.similarity.search('pool" OR NOT (text:', kind=None)

            assert [match.reference for match in found] == [STORED_REFERENCE]

        def test_kind_filter_leaves_out_other_kinds(self, stocked: SimilarityHarness) -> None:
            assert stocked.similarity.search(NEAR_TEXT, kind='crashout') == []

        def test_kind_filter_keeps_the_kind(self, stocked: SimilarityHarness) -> None:
            found = stocked.similarity.search(NEAR_TEXT, kind='ledger-entry')

            assert [match.reference for match in found] == [STORED_REFERENCE]

    class TestRecord:
        @pytest.fixture
        def crowded(self, harness: SimilarityHarness) -> SimilarityHarness:
            writes = [
                create_written(f'ENT-{number}', f'retry pool timeout loop drops word{number}')
                for number in range(CANDIDATE_CAP + 5)
            ]
            harness.similarity.record_all(writes)
            return harness

        @similarity_record_cases()
        def test_duplicate_is_the_closest_match_at_the_threshold(
            self, stocked: SimilarityHarness, case: RecordCase
        ) -> None:
            duplicate = stocked.similarity.record(create_written('ENT-2', case.text))

            assert (duplicate is not None) is case.duplicates_stored
            if duplicate is not None:
                assert (duplicate.written, duplicate.earlier.reference) == (
                    'ENT-2',
                    STORED_REFERENCE,
                )

        def test_first_record_has_no_earlier_duplicate(self, harness: SimilarityHarness) -> None:
            assert harness.similarity.record(create_written('ENT-1', STORED_TEXT)) is None

        def test_recorded_text_is_read_back(self, stocked: SimilarityHarness) -> None:
            assert stocked.similarity.entry('ledger-entry', STORED_REFERENCE) == create_written(
                STORED_REFERENCE, STORED_TEXT
            )

        def test_unknown_entry_reads_back_nothing(self, stocked: SimilarityHarness) -> None:
            assert stocked.similarity.entry('ledger-entry', 'ENT-9') is None

        def test_entry_of_another_kind_reads_back_nothing(self, stocked: SimilarityHarness) -> None:
            assert stocked.similarity.entry('crashout', STORED_REFERENCE) is None

        def test_rerecording_replaces_the_text_and_is_no_duplicate_of_itself(
            self, stocked: SimilarityHarness
        ) -> None:
            revised = create_written(STORED_REFERENCE, UNRELATED_TEXT)

            duplicate = stocked.similarity.record(revised)

            assert (duplicate, stocked.similarity.entry('ledger-entry', STORED_REFERENCE)) == (
                None,
                revised,
            )

        def test_replaced_text_is_no_longer_searchable(self, stocked: SimilarityHarness) -> None:
            stocked.similarity.record(create_written(STORED_REFERENCE, UNRELATED_TEXT))

            assert stocked.similarity.search(NEAR_TEXT, kind=None) == []

        def test_same_reference_under_another_kind_is_a_separate_entry(
            self, stocked: SimilarityHarness
        ) -> None:
            other: Written = create_written(STORED_REFERENCE, NEAR_TEXT, kind='crashout')

            duplicate = stocked.similarity.record(other)

            assert (
                duplicate is not None,
                stocked.similarity.entry('crashout', STORED_REFERENCE),
            ) == (
                True,
                other,
            )

        def test_search_reads_at_most_the_candidate_cap(self, crowded: SimilarityHarness) -> None:
            found = crowded.similarity.search('retry pool timeout loop drops', kind=None)

            assert len(found) == CANDIDATE_CAP

    class TestRecordAll:
        @pytest.fixture
        def batch(self) -> list[Written]:
            return [
                create_written('ENT-1', STORED_TEXT),
                create_written('ENT-2', UNRELATED_TEXT),
                create_written('ENT-3', NEAR_TEXT),
            ]

        def test_empty_batch_has_no_duplicates(self, harness: SimilarityHarness) -> None:
            assert harness.similarity.record_all([]) == []

        def test_later_write_is_compared_with_earlier_writes_of_the_batch(
            self, harness: SimilarityHarness, batch: list[Written]
        ) -> None:
            duplicates = harness.similarity.record_all(batch)

            assert [(item.written, item.earlier.reference) for item in duplicates] == [
                ('ENT-3', 'ENT-1')
            ]

        def test_every_write_of_the_batch_is_stored(
            self, harness: SimilarityHarness, batch: list[Written]
        ) -> None:
            harness.similarity.record_all(batch)

            assert [
                harness.similarity.entry('ledger-entry', item.reference) for item in batch
            ] == batch
