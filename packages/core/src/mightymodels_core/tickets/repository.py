"""The seam under the ticket service: what it asks of the tickets of one repository.

`staged_ticket` refuses a ticket that was never staged. `stage` creates the ticket or replaces
its section, keeps its status, and appends the declared investigations to the ones it already
has; a declared investigation with no record is refused before anything is written.
`unclosed_on_branch` is the one ticket, not closed, whose branch is the one named, and no ticket
when none or more than one is. `all_unclosed_on_branch` names every one of them, in slug order.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import Slug
    from mightymodels_core.tickets.records import TicketRecord, TicketSection


@runtime_checkable
class TicketRepository(Protocol):
    def ticket(self, slug: Slug) -> TicketRecord | None: ...

    def staged_ticket(self, slug: Slug) -> TicketRecord: ...

    def stage(
        self, slug: Slug, section: TicketSection, declared: Sequence[str]
    ) -> TicketRecord: ...

    def mark_in_progress(self, slug: Slug) -> None: ...

    def mark_closed(self, slug: Slug) -> None: ...

    def unclosed_on_branch(self, branch: str) -> Slug | None: ...

    def all_unclosed_on_branch(self, branch: str) -> list[Slug]: ...
