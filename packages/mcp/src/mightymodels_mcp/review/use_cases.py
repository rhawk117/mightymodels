"""The review use cases: sync functions, each opening one `ReviewWork` unit for one tool call.

Core's review unit carries the review and decision services, so the run tools and the decision
tools open it. A unit holds the
database connection synchronously and must never be held across an `await`. A report is read from
the path core builds for it, never from one assembled here.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError, create_routing_table
from mightymodels_core.reviews import parse_report
from mightymodels_core.reviews.policy.review import create_persona_specs
from mightymodels_core.reviews.records import RUNS_LISTED
from mightymodels_core.units_of_work import ReviewWork

from mightymodels_mcp.server.state import create_work

from .views import (
    render_added,
    render_disposed,
    render_gate,
    render_listing,
    render_overridden,
    render_report,
    render_resolved,
    render_started,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import RunId
    from mightymodels_core.reviews import (
        FindingRecord,
        IncomingDisposition,
        ResolveRequest,
        StartRequest,
    )
    from mightymodels_core.vocabulary.reviews import Persona
    from mightymodels_core.workspace import Workspace

    from .schemas import ReportShape
    from .views import ReviewView

REPORT_FILES: dict[Persona, str] = {
    'merge-vader': 'MERGE-VADER-REPORT.md',
    'uncle-bob': 'UNCLE-BOB-REPORT.md',
}


class ReportMissingError(StateError):
    def __init__(self, *, persona: Persona, relative: str) -> None:
        self.persona = persona
        self.relative = relative
        super().__init__(f'no {persona} report at {relative}; the reviewer writes it there first')


def create_review_work(state: OpenState) -> ReviewWork:
    return create_work(state, ReviewWork)


@dataclass(slots=True, kw_only=True, frozen=True)
class StartAtHead:
    request: StartRequest
    head: str | None


def start_review(work: ReviewWork, workspace: Workspace, start: StartAtHead) -> ReviewView:
    with work.write() as unit:
        run = unit.reviews.start(start.request, start.head)

    directory = workspace.review_directory(run.slug, run.run_id)
    directory.mkdir(parents=True, exist_ok=True)
    return render_started(run, workspace.relative_to_root(directory))


def override_review(work: ReviewWork, run_id: RunId) -> ReviewView:
    with work.write() as unit:
        run = unit.reviews.override(run_id)

    return render_overridden(run, create_routing_table())


@dataclass(slots=True, kw_only=True, frozen=True)
class ReportToAdd:
    run_id: RunId
    persona: Persona


def add_review_findings(work: ReviewWork, workspace: Workspace, report: ReportToAdd) -> ReviewView:
    run_id = report.run_id
    persona = report.persona
    with work.write() as unit:
        run = unit.reviews.report(run_id).run
        stored = workspace.persona_report(run.slug, run_id, name=REPORT_FILES[persona])
        if stored.file is None or not stored.file.is_file():
            raise ReportMissingError(persona=persona, relative=stored.relative)

        text = stored.file.read_text(encoding='utf-8')
        incoming = parse_report(text, persona, create_persona_specs())
        added = unit.reviews.add_findings(run_id, incoming)

    return render_added(run_id, added)


def gate_review(work: ReviewWork, run_id: RunId) -> ReviewView:
    with work.read() as unit:
        report = unit.reviews.gate(run_id)

    return render_gate(report)


def report_review(work: ReviewWork, run_id: RunId, shape: ReportShape) -> ReviewView:
    with work.read() as unit:
        report = unit.reviews.report(run_id)

    return render_report(report, shape)


def list_reviews(work: ReviewWork) -> ReviewView:
    with work.read() as unit:
        listing = unit.reviews.listing()

    return render_listing(listing, RUNS_LISTED.rows)


def list_undecided(work: ReviewWork, run_id: RunId) -> tuple[FindingRecord, ...]:
    with work.read() as unit:
        report = unit.reviews.report(run_id)

    gate = report.gate
    ordered = gate.ordered(report.findings)
    return tuple(finding for finding in ordered if gate.decision_of(finding) is None)


@dataclass(slots=True, kw_only=True, frozen=True)
class DispositionsToRecord:
    run_id: RunId
    decisions: Mapping[str, IncomingDisposition]
    by: str


def dispose_findings(work: ReviewWork, dispositions: DispositionsToRecord) -> ReviewView:
    run_id = dispositions.run_id
    with work.write() as unit:
        disposed = unit.decisions.dispose(run_id, dispositions.decisions, dispositions.by)

    return render_disposed(run_id, disposed)


def resolve_finding(work: ReviewWork, run_id: RunId, request: ResolveRequest) -> ReviewView:
    with work.write() as unit:
        resolved = unit.decisions.resolve(run_id, request)

    return render_resolved(run_id, resolved)
