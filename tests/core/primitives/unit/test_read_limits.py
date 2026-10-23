from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import ReadLimit, ReadLimitError, WriteLimitError

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet


@dataclass(slots=True, kw_only=True, frozen=True)
class LatestScenario:
    name: str
    newest_first: tuple[int, ...]
    expected_rows: tuple[int, ...]
    expected_left_out: bool

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def read_limit_latest_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'scenario',
        [
            LatestScenario(
                name='under the limit',
                newest_first=(2, 1),
                expected_rows=(1, 2),
                expected_left_out=False,
            ).param,
            LatestScenario(
                name='at the limit',
                newest_first=(3, 2, 1),
                expected_rows=(1, 2, 3),
                expected_left_out=False,
            ).param,
            LatestScenario(
                name='past the limit',
                newest_first=(5, 4, 3, 2, 1),
                expected_rows=(3, 4, 5),
                expected_left_out=True,
            ).param,
            LatestScenario(
                name='empty',
                newest_first=(),
                expected_rows=(),
                expected_left_out=False,
            ).param,
        ],
    )


class TestReadLimit:
    owner = 'the task table'
    limit = ReadLimit(rows=3, kept='tasks')

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

    @read_limit_latest_cases()
    def test_latest_keeps_the_newest_rows_oldest_first(self, scenario: LatestScenario) -> None:
        latest = self.limit.latest(scenario.newest_first)
        assert latest.rows == scenario.expected_rows
        assert latest.older_left_out is scenario.expected_left_out
