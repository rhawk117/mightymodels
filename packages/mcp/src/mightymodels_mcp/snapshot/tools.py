"""The snapshot tool: a thin async handler over the sync use case, and its registration.

It asks git for the branch, HEAD and the dirty paths, takes the snapshot in one read unit and
returns it. It writes no file; the agent writes the Markdown and the record at the paths returned.
"""

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations
from mightymodels_core.git import UntrackedFiles
from mightymodels_core.snapshot import SnapshotRequest
from mightymodels_core.snapshot.records import RepositoryFacts
from mightymodels_core.workspace import workspace_at

from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolDefinition

from .schemas import SnapshotTakeRequest
from .use_cases import create_snapshot_work, take_snapshot
from .views import SnapshotView

if TYPE_CHECKING:
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext

READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)


async def snapshot_take(request: SnapshotTakeRequest, ctx: ToolContext) -> SnapshotView:
    """Take a snapshot of a staged ticket; changes nothing, the agent writes the two files."""
    async with ctx.request_context.lifespan_context.state.open() as state:
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


def register_snapshot_tools(catalog: ToolCatalog) -> ToolCatalog:
    take = ToolDefinition(
        name='snapshot_take',
        title='Take a snapshot',
        annotations=READS,
        icon=load_icon('snapshot'),
        request_model=SnapshotTakeRequest,
        result_model=SnapshotView,
        handler=snapshot_take,
    )
    return catalog.register(take)
