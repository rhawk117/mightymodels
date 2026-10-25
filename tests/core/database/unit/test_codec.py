from datetime import datetime

import pytest
from mightymodels_core.database import NaiveTimestampError, RowDecodeError, bind_params, decode_row

from tests.core.database.database_builders import ECHO, EchoParams


class TestBindParams:
    @pytest.fixture
    def naive_params(self) -> EchoParams:
        return EchoParams(
            items=[],
            mapping={},
            at=datetime.fromisoformat('2024-01-01T00:00:00'),
            color='red',
            flag=True,
        )

    def test_a_datetime_without_a_timezone_is_rejected(self, naive_params: EchoParams) -> None:
        with pytest.raises(NaiveTimestampError) as raised:
            bind_params(naive_params)

        assert raised.value.field == 'at'


class TestDecodeRow:
    def test_a_row_that_does_not_fit_the_struct_is_rejected(self) -> None:
        with pytest.raises(RowDecodeError) as raised:
            decode_row(ECHO, '{"items": "nope"}')

        assert raised.value.statement == 'echo'
