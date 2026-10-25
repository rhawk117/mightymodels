from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, get_args

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.database import ConnectionOptions, open_database

from tests.core.database.database_builders import ECHO, Color, EchoParams

if TYPE_CHECKING:
    from mightymodels_core.database import DatabaseSpec

    from tests.core.database.database_builders import EchoRow


def echo(spec: DatabaseSpec, params: EchoParams) -> EchoRow:
    options = ConnectionOptions(journal_mode='MEMORY')
    with closing(open_database(Path(':memory:'), spec, options)) as opened, opened.read() as unit:
        row = unit.one(ECHO, params)
    assert row is not None
    return row


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
        color=st.sampled_from(get_args(Color.__value__)),
        flag=st.booleans(),
    )

    @pytest.mark.regression
    @given(params=params)
    @example(
        params=EchoParams(
            items=[],
            mapping={},
            at=datetime(3059, 1, 1, 0, 0, 0, 999997, tzinfo=UTC),
            color='red',
            flag=False,
        )
    )
    def test_bound_params_read_back_equal(
        self, echo_spec: DatabaseSpec, params: EchoParams
    ) -> None:
        row = echo(echo_spec, params)

        assert row.items == params.items
        assert row.mapping == params.mapping
        assert row.at == params.at.replace(microsecond=0)
        assert row.color == params.color
        assert row.flag == params.flag
