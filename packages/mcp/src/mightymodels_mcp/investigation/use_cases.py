"""The investigation use cases: sync functions, each opening one `InvestigationWork` unit.

A unit holds the database connection synchronously and must never be held across an `await`, so
a tool asks git for HEAD first and passes the answer in. Start and add open a write unit; render,
knowns and list open a read unit.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.units_of_work import InvestigationWork

from mightymodels_mcp.server.state import create_work

from .views import (
    render_added,
    render_knowns,
    render_ledger,
    render_listing,
    render_started,
)

if TYPE_CHECKING:
    from mightymodels_core.edge import OpenState
    from mightymodels_core.investigations import AddRequest, KnownsSelection, StartRequest
    from mightymodels_core.primitives import Slug

    from .views import InvestigationView


def create_investigation_work(state: OpenState) -> InvestigationWork:
    return create_work(state, InvestigationWork)


def start_investigation(work: InvestigationWork, request: StartRequest) -> InvestigationView:
    with work.write() as unit:
        started = unit.investigations.start(request)

    return render_started(started)


def add_to_investigation(
    work: InvestigationWork, investigation: Slug, request: AddRequest
) -> InvestigationView:
    with work.write() as unit:
        added = unit.investigations.add(investigation, request)

    return render_added(added)


def render_investigation(work: InvestigationWork, investigation: Slug) -> InvestigationView:
    with work.read() as unit:
        ledger = unit.investigations.render(investigation)

    return render_ledger(ledger)


@dataclass(slots=True, kw_only=True, frozen=True)
class KnownsAtHead:
    investigation: Slug
    selection: KnownsSelection
    head: str | None


def show_knowns(work: InvestigationWork, asked: KnownsAtHead) -> InvestigationView:
    with work.read() as unit:
        knowns = unit.investigations.knowns(asked.investigation, asked.selection, asked.head)

    return render_knowns(knowns)


def list_investigations(work: InvestigationWork) -> InvestigationView:
    with work.read() as unit:
        listed = unit.investigations.list_rounds()

    return render_listing(listed)
