import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.primitives import ReadLimit, ReadLimitError, WriteLimitError


class TestReadLimit:
    owner = 'the task table'
    limit = ReadLimit(rows=3, kept='tasks')
    newest_first_rows = st.lists(st.integers())

    @pytest.fixture
    def refusal(self) -> ReadLimitError | None:
        return self.limit.error([1, 2, 3, 4], owner=self.owner)

    def test_fetched_asks_for_one_row_past_the_limit(self) -> None:
        assert self.limit.fetched == 4

    def test_read_at_the_limit_is_kept(self) -> None:
        assert self.limit.error([1, 2, 3], owner=self.owner) is None

    def test_read_one_past_the_limit_is_refused(self, refusal: ReadLimitError | None) -> None:
        assert isinstance(refusal, ReadLimitError)

    def test_refusal_names_owner_rows_and_kept(self, refusal: ReadLimitError | None) -> None:
        assert refusal is not None
        assert (refusal.owner, refusal.rows, refusal.kept) == (self.owner, 3, 'tasks')
        assert 'the task table holds more than 3 tasks' in str(refusal)

    def test_write_at_the_cap_is_kept(self) -> None:
        assert self.limit.write_error(3, owner=self.owner) is None

    def test_write_past_the_cap_is_refused(self) -> None:
        refusal = self.limit.write_error(4, owner=self.owner)
        assert isinstance(refusal, WriteLimitError)
        assert (refusal.owner, refusal.rows, refusal.kept) == (self.owner, 3, 'tasks')
        assert 'the task table would hold more than 3 tasks' in str(refusal)

    @given(newest_first=newest_first_rows)
    @example(newest_first=[2, 1])
    @example(newest_first=[3, 2, 1])
    @example(newest_first=[5, 4, 3, 2, 1])
    @example(newest_first=[])
    def test_latest_keeps_the_newest_rows_oldest_first(self, newest_first: list[int]) -> None:
        latest = self.limit.latest(newest_first)

        assert list(reversed(latest.rows)) == newest_first[: self.limit.rows]
        assert latest.older_left_out is (len(newest_first) > self.limit.rows)
