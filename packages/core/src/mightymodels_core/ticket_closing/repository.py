"""The seam under the close service: the one closing of a ticket, by ticket id.

`record_closing` writes the closing of a ticket and replaces the one it already has. It does not
mark the ticket closed, and it does not check that the ticket exists; the ticket repository and
the unit of work own both. `closing` is the record of a ticket, or none when it was never closed.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mightymodels_core.ticket_closing.records import ClosingRecord


@runtime_checkable
class ClosingRepository(Protocol):
    def record_closing(self, ticket_id: int, record: ClosingRecord) -> None: ...

    def closing(self, ticket_id: int) -> ClosingRecord | None: ...
