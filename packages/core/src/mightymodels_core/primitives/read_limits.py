"""The most rows one read returns, and the refusals when a read or a write would pass it."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import ReadLimitError, WriteLimitError

if TYPE_CHECKING:
    from collections.abc import Sequence, Sized


@dataclass(slots=True, kw_only=True, frozen=True)
class Latest[Row]:
    rows: tuple[Row, ...]
    older_left_out: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class ReadLimit:
    rows: int
    kept: str

    @property
    def fetched(self) -> int:
        return self.rows + 1

    def error(self, fetched: Sized, *, owner: str) -> ReadLimitError | None:
        if len(fetched) <= self.rows:
            return None
        return ReadLimitError(owner=owner, rows=self.rows, kept=self.kept)

    def write_error(self, held: int, *, owner: str) -> WriteLimitError | None:
        if held <= self.rows:
            return None
        return WriteLimitError(owner=owner, rows=self.rows, kept=self.kept)

    def latest[Row](self, newest_first: Sequence[Row]) -> Latest[Row]:
        return Latest(
            rows=tuple(reversed(newest_first[: self.rows])),
            older_left_out=len(newest_first) > self.rows,
        )
