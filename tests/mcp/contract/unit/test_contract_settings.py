import pytest
from mightymodels_core.contract.runs import RunOptions
from mightymodels_mcp.contract.settings import (
    HEARTBEAT_VARIABLE,
    InvalidHeartbeatError,
    parse_run_options,
)


def valid_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        ('given', 'seconds'),
        [
            pytest.param('0.5', 0.5, id='fraction'),
            pytest.param('2', 2.0, id='integer'),
            pytest.param(' 3 ', 3.0, id='padded'),
        ],
    )


def invalid_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'given',
        [
            pytest.param('soon', id='not-a-number'),
            pytest.param('', id='empty'),
            pytest.param('0', id='zero'),
            pytest.param('-1', id='negative'),
            pytest.param('nan', id='nan'),
            pytest.param('inf', id='inf'),
            pytest.param('-inf', id='negative-inf'),
        ],
    )


class TestParseRunOptions:
    def test_unset_keeps_the_default_interval(self) -> None:
        assert parse_run_options({}) == RunOptions()

    @valid_cases()
    def test_a_finite_positive_number_sets_the_interval(self, given: str, seconds: float) -> None:
        options = parse_run_options({HEARTBEAT_VARIABLE: given})

        assert options == RunOptions(heartbeat_seconds=seconds)

    @invalid_cases()
    def test_anything_else_is_refused_naming_the_variable_and_value(self, given: str) -> None:
        refusal = parse_run_options({HEARTBEAT_VARIABLE: given})

        assert isinstance(refusal, InvalidHeartbeatError)
        assert refusal.given == given
        assert str(refusal) == (
            f'{HEARTBEAT_VARIABLE} is {given!r}; it must be a finite number above zero'
        )
