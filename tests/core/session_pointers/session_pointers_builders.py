"""The fixed clock and pointer factory the session pointer tests share."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from mightymodels_core.session_pointers import SqliteSessionPointerRepository

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@dataclass(slots=True, kw_only=True, frozen=True)
class FixedClock:
    moment: datetime

    def now(self) -> datetime:
        return self.moment


type PointersAt = Callable[[str, datetime], SqliteSessionPointerRepository]
