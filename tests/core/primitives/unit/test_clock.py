from datetime import UTC, datetime, timedelta, timezone

import pytest
from mightymodels_core.database.codec import bind_value
from mightymodels_core.primitives import Clock, from_unixepoch
from mightymodels_core.primitives.clock import SystemClock
from mightymodels_core.primitives.errors import NaiveClockTimeError

from tests.core.primitives.clock import FakeClock, create_fake_clock


def clock_protocol_cases() -> pytest.MarkDecorator:
    moment = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    clocks = [
        pytest.param(SystemClock(), id='system'),
        pytest.param(FakeClock(moments=[moment]), id='fake'),
    ]
    return pytest.mark.parametrize('clock', clocks)


class TestFromUnixepoch:
    moment = datetime(2026, 10, 19, 12, 30, 45, 999_999, tzinfo=UTC)
    offset_moment = datetime(2026, 10, 19, 14, 30, 45, tzinfo=timezone(timedelta(hours=2)))

    def test_round_trips_through_the_database_codec(self) -> None:
        seconds = bind_value('created_at', self.moment)
        assert isinstance(seconds, int)

        restored = from_unixepoch(seconds)

        assert restored == self.moment.replace(microsecond=0)
        assert restored.utcoffset() == timedelta(0)

    def test_offset_moment_comes_back_as_utc(self) -> None:
        seconds = bind_value('created_at', self.offset_moment)
        assert isinstance(seconds, int)

        restored = from_unixepoch(seconds)

        assert restored == self.offset_moment
        assert restored.tzinfo is UTC


class TestClocks:
    moment = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    naive_moment = datetime.fromisoformat('2026-10-19T12:00:00')

    @pytest.fixture
    def fake_clock(self) -> FakeClock:
        return create_fake_clock(self.moment)

    def test_system_clock_returns_a_utc_aware_datetime(self) -> None:
        reading = SystemClock().now()

        assert reading.tzinfo is UTC

    def test_fake_clock_refuses_a_naive_datetime(self) -> None:
        with pytest.raises(NaiveClockTimeError):
            create_fake_clock(self.naive_moment)

    def test_fake_clock_reads_the_time_last_set(self, fake_clock: FakeClock) -> None:
        later = self.moment + timedelta(hours=1)

        fake_clock.set_now(later)

        assert fake_clock.now() == later

    @clock_protocol_cases()
    def test_clocks_satisfy_the_protocol(self, clock: object) -> None:
        assert isinstance(clock, Clock)
