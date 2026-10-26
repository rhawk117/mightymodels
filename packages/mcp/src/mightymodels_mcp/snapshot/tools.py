"""The snapshot tool: a thin async handler over the sync use case, and its registration.

It asks git for the branch, HEAD and the dirty paths, takes the snapshot in one read unit and
returns it. It writes no file; the agent writes the Markdown and the record at the paths returned.
"""

from typing import TYPE_CHECKING

from mightymodels_core.git import UntrackedFiles
from mightymodels_core.snapshot import SnapshotRequest
from mightymodels_core.snapshot.records import RepositoryFacts
from mightymodels_core.workspace import workspace_at

from mightymodels_mcp.server.annotations import READS
from mightymodels_mcp.server.registration import ToolSpec, open_tool_state, register_specs

from .schemas import SnapshotTakeRequest
from .use_cases import create_snapshot_work, take_snapshot
from .views import SnapshotView

if TYPE_CHECKING:
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext


async def snapshot_take(request: SnapshotTakeRequest, ctx: ToolContext) -> SnapshotView:
    """Take a snapshot of a staged ticket; changes nothing, the agent writes the two files."""
    async with open_tool_state(ctx) as state:
        git = state.git
        refusal = await git.refusal()
        branch = await git.current_branch()
        head = await git.resolve_head()
        dirty = await git.dirty_paths(untracked=UntrackedFiles.NORMAL)
        facts = RepositoryFacts(
            branch=branch,
            head=head,
            dirty=None if dirty is None else tuple(dirty),
            refusal=refusal,
        )
        asked = SnapshotRequest(slug=request.slug, repository=facts, limit=request.limit)
        workspace = workspace_at(state.checkout.toplevel)
        return take_snapshot(create_snapshot_work(state), workspace, asked)


SNAPSHOT_TOOLS = (
    ToolSpec(
        name='snapshot_take',
        title='Take a snapshot',
        annotations=READS,
        icon='snapshot',
        request_model=SnapshotTakeRequest,
        result_model=SnapshotView,
        handler=snapshot_take,
    ),
)


def register_snapshot_tools(catalog: ToolCatalog) -> ToolCatalog:
    return register_specs(catalog, SNAPSHOT_TOOLS)
