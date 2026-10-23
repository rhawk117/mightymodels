"""The closing repository over a core unit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact
from mightymodels_core.schemas.tickets import (
    CLOSING_OF_TICKET,
    UPSERT_CLOSING,
    ClosingParams,
    UpsertClosingParams,
)
from mightymodels_core.ticket_closing.records import ClosingRecord

if TYPE_CHECKING:
    from mightymodels_core.database import Unit
    from mightymodels_core.schemas.tickets import ClosingRow


def record_of(row: ClosingRow) -> ClosingRecord:
    return ClosingRecord(
        closed_at=row.closed_at,
        head=row.head,
        shipped=redact(row.shipped),
        pr=row.pr,
        gotchas=tuple(redact(gotcha) for gotcha in row.gotchas),
        archive=row.archive,
    )


def upsert_params_of(ticket_id: int, record: ClosingRecord) -> UpsertClosingParams:
    return UpsertClosingParams(
        ticket_id=ticket_id,
        closed_at=record.closed_at,
        head=record.head,
        shipped=record.shipped,
        pr=record.pr,
        gotchas=list(record.gotchas),
        archive=record.archive,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteClosingRepository:
    unit: Unit

    def record_closing(self, ticket_id: int, record: ClosingRecord) -> None:
        self.unit.run(UPSERT_CLOSING, upsert_params_of(ticket_id, record))

    def closing(self, ticket_id: int) -> ClosingRecord | None:
        row = self.unit.one(CLOSING_OF_TICKET, ClosingParams(ticket_id=ticket_id))
        return None if row is None else record_of(row)
