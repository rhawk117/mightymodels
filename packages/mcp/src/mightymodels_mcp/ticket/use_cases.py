"""The ticket use cases: sync functions, each opening one `TicketWork` unit for one tool call.

They are the only place a ticket unit of work opens, because a unit holds the database
connection synchronously and must never be held across an `await`.
"""

from typing import TYPE_CHECKING

from mightymodels_core.edge import create_clock
from mightymodels_core.ticket_closing.errors import LiveWorkRemainsError
from mightymodels_core.ticket_closing.services import CloseRequest
from mightymodels_core.units_of_work import TicketWork
from mightymodels_core.workspace import workspace_at

from .archive import free_archive_files, write_archive
from .close_facts import PreparedClose
from .views import (
    ArchivePathsView,
    render_blocked,
    render_close_check,
    render_closed,
    render_staged,
    render_written,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import Slug
    from mightymodels_core.ticket_closing.records import CloseFacts
    from mightymodels_core.tickets import TicketAnswers

    from .close_facts import CloseAttempt
    from .views import CloseView, TicketView

VALID_LEAD = 'valid; '
CONTEXT_UPDATED_LEAD = 'context updated; '
NOT_CLOSED_HEADING = 'not closed; live work remains'


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


def prepare_close(work: TicketWork, slug: Slug) -> PreparedClose:
    with work.read() as unit:
        seen = unit.closing.prepare(slug)

    debug_note = work.workspace.handoffs.live_debug(slug).is_file()
    return PreparedClose(seen=seen, debug_note=debug_note)


def check_close(work: TicketWork, slug: Slug, facts: CloseFacts) -> CloseView:
    with work.read() as unit:
        check = unit.closing.check(slug, facts)

    return render_close_check(slug, check)


def archive_closed(work: TicketWork, attempt: CloseAttempt) -> CloseView:
    workspace = work.workspace
    slug = attempt.slug
    with work.write() as unit:
        files = free_archive_files(workspace, slug)
        request = CloseRequest(
            seen=attempt.prepared.seen,
            facts=attempt.facts,
            lines=attempt.lines,
            archive=workspace.relative_to_root(files.markdown),
        )
        closed = unit.closing.close(slug, request)
        write_archive(files, closed.archive, decision_limit=unit.closing.options.decision_limit)

    paths = ArchivePathsView(
        markdown_path=workspace.relative_to_root(files.markdown),
        record_path=workspace.relative_to_root(files.record),
    )
    return render_closed(slug, paths, attempt.facts.git_refusal)


def close_ticket_work(work: TicketWork, attempt: CloseAttempt) -> CloseView:
    try:
        return archive_closed(work, attempt)
    except LiveWorkRemainsError as remains:
        return render_blocked(NOT_CLOSED_HEADING, remains.blockers, remains.git_refusal)
