import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from enum import StrEnum, auto
from typing import Any

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.database import (
    NaiveTimestampError,
    Query,
    RowDecodeError,
    bind_params,
    decode_row,
)
from msgspec import Struct

pytestmark = pytest.mark.integration


class Color(StrEnum):
    RED = auto()
    GREEN = auto()


class EchoParams(Struct, frozen=True, kw_only=True):
    items: list[Any]
    mapping: dict[str, Any]
    at: datetime
    color: Color
    flag: bool


class EchoRow(Struct, frozen=True, kw_only=True):
    items: list[Any]
    mapping: dict[str, Any]
    at: datetime
    color: Color
    flag: bool


ECHO = Query(name='echo', params=EchoParams, row=EchoRow)

ECHO_SQL = """
SELECT json_object(
    'items', json(:items),
    'mapping', json(:mapping),
    'at', strftime('%Y-%m-%dT%H:%M:%SZ', :at, 'unixepoch'),
    'color', :color,
    'flag', :flag
) AS row
"""


def echo(params: EchoParams) -> EchoRow:
    with closing(sqlite3.connect(':memory:')) as connection:
        (row,) = connection.execute(ECHO_SQL, bind_params(params)).fetchone()
    return decode_row(ECHO, row)


class TestRoundTrip:
    json_values = st.recursive(
        st.none() | st.booleans() | st.integers(-(2**53), 2**53) | st.text(),
        lambda children: (
            st.lists(children, max_size=4) | st.dictionaries(st.text(), children, max_size=4)
        ),
        max_leaves=12,
    )
    params = st.builds(
        EchoParams,
        items=st.lists(json_values, max_size=4),
        mapping=st.dictionaries(st.text(), json_values, max_size=4),
        at=st.datetimes(timezones=st.just(UTC)),
        color=st.sampled_from(Color),
        flag=st.booleans(),
    )

    @pytest.mark.regression
    @given(params=params)
    @example(
        params=EchoParams(
            items=[],
            mapping={},
            at=datetime(3059, 1, 1, 0, 0, 0, 999997, tzinfo=UTC),
            color=Color.RED,
            flag=False,
        )
    )
    def test_bound_params_read_back_equal(self, params: EchoParams) -> None:
        row = echo(params)

        assert row.items == params.items
        assert row.mapping == params.mapping
        assert row.at == params.at.replace(microsecond=0)
        assert row.color is params.color
        assert row.flag is params.flag


class TestBindParams:
    def test_a_datetime_without_a_timezone_is_rejected(self) -> None:
        params = EchoParams(
            items=[],
            mapping={},
            at=datetime.fromisoformat('2024-01-01T00:00:00'),
            color=Color.RED,
            flag=True,
        )

        with pytest.raises(NaiveTimestampError) as raised:
            bind_params(params)

        assert raised.value.field == 'at'


class TestDecodeRow:
    def test_a_row_that_does_not_fit_the_struct_is_rejected(self) -> None:
        with pytest.raises(RowDecodeError) as raised:
            decode_row(ECHO, '{"items": "nope"}')

        assert raised.value.statement == 'echo'
