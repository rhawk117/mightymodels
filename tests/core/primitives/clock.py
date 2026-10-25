"""A clock whose current time is set by the test."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.primitives.errors import NaiveClockTimeError

if TYPE_CHECKING:
    from datetime import datetime


def get_clock_time_problem(moment: datetime) -> NaiveClockTimeError | None:
    if moment.tzinfo is None:
        return NaiveClockTimeError(moment=moment)

    return None


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeClock:
    moments: list[datetime] = field(default_factory=list)

    def now(self) -> datetime:
        return self.moments[-1]

    def set_now(self, moment: datetime) -> None:
        if problem := get_clock_time_problem(moment):
            raise problem

        self.moments.append(moment)


def create_fake_clock(moment: datetime) -> FakeClock:
    clock = FakeClock()
    clock.set_now(moment)
    return clock
