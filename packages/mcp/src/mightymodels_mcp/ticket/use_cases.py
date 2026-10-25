"""The ticket use cases: sync functions, each opening one `TicketWork` unit for one tool call.

They are the only place a ticket unit of work opens, because a unit holds the database
connection synchronously and must never be held across an `await`.
"""

from typing import TYPE_CHECKING

from mightymodels_core.edge import create_clock
from mightymodels_core.units_of_work import TicketWork
from mightymodels_core.workspace import workspace_at

from .views import render_staged, render_written

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import Slug
    from mightymodels_core.tickets import TicketAnswers

    from .views import TicketView

VALID_LEAD = 'valid; '
CONTEXT_UPDATED_LEAD = 'context updated; '


def create_ticket_work(state: OpenState) -> TicketWork:
    checkout = state.checkout
    return TicketWork(
        database=state.database,
        repository_key=checkout.repository_key(),
        workspace=workspace_at(checkout.toplevel),
        clock=create_clock(),
    )


def write_ticket(work: TicketWork, slug: Slug, answers: TicketAnswers) -> TicketView:
    with work.write() as unit:
        slot = unit.files.slot(slug)
        text = unit.tickets.write(slug, answers, slot)
        unit.store(slug, text)

    return render_written(slot.path)


def validate_ticket(work: TicketWork, slug: Slug) -> TicketView:
    with work.write() as unit:
        record = unit.tickets.stage(slug, unit.files.source(slug))

    return render_staged(record, VALID_LEAD)


def show_ticket(work: TicketWork, slug: Slug) -> TicketView:
    with work.read() as unit:
        record = unit.tickets.show(slug)

    return render_staged(record)


def update_ticket_context(work: TicketWork, slug: Slug, context: Sequence[str]) -> TicketView:
    with work.write() as unit:
        update = unit.tickets.update_context(slug, unit.files.source(slug), context)
        unit.store(slug, update.text)

    return render_staged(update.record, CONTEXT_UPDATED_LEAD)
