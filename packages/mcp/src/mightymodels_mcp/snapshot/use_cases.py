"""The snapshot use case: a sync function opening one read unit for one tool call.

The unit holds the database connection synchronously and must never be held across an `await`, so
the tool asks git first and passes the answer in. Nothing is written: the paths come back for the
agent to write the two files.
"""

from typing import TYPE_CHECKING

from mightymodels_core.units_of_work import SnapshotRead

from mightymodels_mcp.server.state import create_work

from .views import render_snapshot

if TYPE_CHECKING:
    from mightymodels_core.edge import OpenState
    from mightymodels_core.snapshot import SnapshotRequest
    from mightymodels_core.workspace import Workspace

    from .views import SnapshotView


def create_snapshot_work(state: OpenState) -> SnapshotRead:
    return create_work(state, SnapshotRead)


def take_snapshot(
    work: SnapshotRead,
    workspace: Workspace,
    request: SnapshotRequest,
) -> SnapshotView:
    with work.read() as unit:
        record = unit.snapshots.take(request)

    files = workspace.handoffs.snapshot(request.slug)
    return render_snapshot(
        record,
        markdown_path=workspace.relative_to_root(files.markdown),
        record_path=workspace.relative_to_root(files.record),
    )
