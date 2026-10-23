"""A closing repository kept in memory."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mightymodels_core.ticket_closing.records import ClosingRecord


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeClosingRepository:
    records: dict[int, ClosingRecord] = field(default_factory=dict)

    def record_closing(self, ticket_id: int, record: ClosingRecord) -> None:
        self.records[ticket_id] = record

    def closing(self, ticket_id: int) -> ClosingRecord | None:
        return self.records.get(ticket_id)
