"""The clock every service reads the time from, and the unixepoch conversion back."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(tz=UTC)


def from_unixepoch(seconds: int) -> datetime:
    return EPOCH + timedelta(seconds=seconds)
