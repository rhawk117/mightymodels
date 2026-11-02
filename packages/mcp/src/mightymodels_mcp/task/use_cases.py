"""The task use cases: sync functions, each opening one `TaskWork` unit for one tool call.

They are the only place a task unit of work opens, because a unit holds the database connection
synchronously and must never be held across an `await`. Every use case reads the attempt counts of
the records it returns from the same unit.
"""

from typing import TYPE_CHECKING

from mightymodels_core.tasks import VerdictPolicy
from mightymodels_core.units_of_work import TaskWork

from mightymodels_mcp.server.state import create_work

from .schemas import create_mark_request, create_start_request
from .views import (
    StartOrigin,
    render_fix_recorded,
    render_listing,
    render_marked,
    render_readiness,
    render_started,
    render_verified,
)

if TYPE_CHECKING:
    from mightymodels_core.edge import OpenState
    from mightymodels_core.primitives import Slug
    from mightymodels_core.tasks import VerifyRequest
    from mightymodels_core.tasks.records import TaskRecord

    from .schemas import (
        FailedFixRequest,
        TaskDeclareRequest,
        TaskMarkRequest,
        TaskStartRequest,
        TaskVerifyRequest,
    )
    from .views import TaskView, VerifyView


def create_task_work(state: OpenState) -> TaskWork:
    return create_work(state, TaskWork)


def start_task(work: TaskWork, request: TaskStartRequest, head: str | None) -> TaskView:
    with work.write() as unit:
        start_request = create_start_request(request, head)
        record = unit.tasks.start(request.slug, start_request)
        warning = unit.tasks.get_size_warning(start_request)
        attempts = unit.task_reads.show(request.slug).attempts

    origin = StartOrigin(worker=request.by, head=head, warning=warning)
    return render_started(record, attempts, origin)


def declare_tasks(work: TaskWork, request: TaskDeclareRequest) -> TaskView:
    with work.write() as unit:
        records = unit.tasks.declare(request.slug, request.task_ids)
        attempts = unit.task_reads.show(request.slug).attempts

    return render_listing(records, attempts)


def prepare_verification(work: TaskWork, request: TaskVerifyRequest) -> TaskRecord:
    with work.read() as unit:
        verdict = VerdictPolicy(
            task_key=request.task_id, verdict=request.verdict, reason=request.reason
        )
        return unit.tasks.prepare_verification(request.slug, verdict)


def verify_task(work: TaskWork, slug: Slug, request: VerifyRequest) -> VerifyView:
    with work.write() as unit:
        record = unit.tasks.verify(slug, request)
        attempts = unit.task_reads.show(slug).attempts

    return render_verified(record, attempts, request)


def mark_task(work: TaskWork, request: TaskMarkRequest) -> TaskView:
    with work.write() as unit:
        record = unit.tasks.mark(request.slug, create_mark_request(request))
        attempts = unit.task_reads.show(request.slug).attempts

    return render_marked(record, attempts, request.reason)


def show_tasks(work: TaskWork, slug: Slug) -> TaskView:
    with work.read() as unit:
        listing = unit.task_reads.show(slug)

    return render_listing(listing.records, listing.attempts)


def check_ready(work: TaskWork, slug: Slug, head: str | None) -> TaskView:
    with work.read() as unit:
        readiness = unit.task_reads.ready(slug)
        attempts = unit.task_reads.show(slug).attempts

    return render_readiness(readiness, attempts, head)


def record_failed_fix(work: TaskWork, request: FailedFixRequest) -> TaskView:
    with work.write() as unit:
        recorded = unit.tasks.record_failed_fix(request.slug, request.task_id, request.hypothesis)

    return render_fix_recorded(request.task_id, recorded)
