"""The pure matching rules of the similarity store."""

from hypothesis import given
from hypothesis import strategies as st
from mightymodels_core.similarity import (
    CANDIDATE_CAP,
    MATCH_OVERLAP,
    content_words,
    overlap,
)
from mightymodels_core.similarity.matching import index_query


class TestMatching:
    words = st.lists(st.sampled_from(('retry', 'pool', 'timeout', 'loop', 'drops')), min_size=1)

    def test_content_words_drop_common_words_and_redaction_markers(self) -> None:
        text = 'The key [REDACTED:api-key] is in the Pool'

        assert content_words(text) == {'key', 'pool'}

    def test_content_words_split_at_punctuation_and_case(self) -> None:
        assert content_words('Retry-Loop, retry_loop; POOL2') == {'retry', 'loop', 'pool2'}

    def test_overlap_of_two_empty_sets_is_zero(self) -> None:
        assert overlap(frozenset(), frozenset()) == 0.0

    def test_overlap_is_the_shared_share_of_both(self) -> None:
        assert overlap(frozenset('abc'), frozenset('bcd')) == 0.5

    @given(words=words)
    def test_a_text_overlaps_itself_completely(self, words: list[str]) -> None:
        assert overlap(frozenset(words), frozenset(words)) == 1.0

    def test_index_query_quotes_each_word_and_orders_them(self) -> None:
        assert index_query({'pool', 'retry'}) == '"pool" OR "retry"'

    def test_threshold_and_cap_are_the_ported_values(self) -> None:
        assert (MATCH_OVERLAP, CANDIDATE_CAP) == (0.6, 20)
