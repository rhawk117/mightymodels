"""The `pre-compact` subcommand, which the PreCompact hook runs.

A compaction drops the conversation, so before it runs the hook writes the snapshot of the one
ticket, not closed, whose branch is checked out: the same record and Markdown the `snapshot` tool
serves, to the ticket's `handoffs/snapshot.json` and `handoffs/snapshot.md`, for the next turn to
resume from. It reads the state database and git and writes those two files. A detached HEAD, a
branch no open ticket names and a branch two open tickets name leave everything as it was.

The hook never blocks a compaction and prints nothing on standard output. No ticket directory, no
data directory, no git work tree, an unreadable database or an unwritable handoffs directory is said
on standard error, with exit 0.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, TextIO

from mightymodels_core.edge import create_clock, open_state
from mightymodels_core.git import UntrackedFiles
from mightymodels_core.primitives import encode_indented
from mightymodels_core.snapshot import SnapshotRequest, snapshot_markdown
from mightymodels_core.snapshot.records import RepositoryFacts
from mightymodels_core.units_of_work import SnapshotRead, UnknownRepositoryError
from mightymodels_core.workspace import workspace_at

from mightymodels_hooks.hook_context import (
    STATE_UNREADABLE,
    ShortTimeoutBackends,
    create_hook_context_at,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.git import Git
    from mightymodels_core.snapshot import SnapshotRecord
    from mightymodels_core.workspace import RecordFiles

    from mightymodels_hooks.hook_context import HookContext
    from mightymodels_hooks.payloads import PreCompactPayload


async def repository_facts(git: Git) -> RepositoryFacts:
    refusal = await git.refusal()
    branch = await git.current_branch()
    head = await git.resolve_head()
    dirty = await git.dirty_paths(untracked=UntrackedFiles.NORMAL)
    return RepositoryFacts(
        branch=branch,
        head=head,
        dirty=None if dirty is None else tuple(dirty),
        refusal=refusal,
    )


def take_on_branch(work: SnapshotRead, facts: RepositoryFacts) -> SnapshotRecord | None:
    with work.read() as unit:
        slug = (
            None
            if facts.branch is None
            else unit.snapshots.tickets.unclosed_on_branch(facts.branch)
        )
        if slug is None:
            return None

        return unit.snapshots.take(SnapshotRequest(slug=slug, repository=facts))


def write_files(files: RecordFiles, record: SnapshotRecord) -> None:
    files.record.parent.mkdir(parents=True, exist_ok=True)
    files.record.write_bytes(encode_indented(record))
    files.markdown.write_text(snapshot_markdown(record), encoding='utf-8')


async def write_snapshot(context: HookContext) -> None:
    async with open_state(
        context.data_directory(), context.start(), backends=ShortTimeoutBackends()
    ) as state:
        facts = await repository_facts(state.git)
        work = SnapshotRead(
            database=state.database,
            repository_key=state.checkout.repository_key(),
            clock=create_clock(),
        )
        record = take_on_branch(work, facts)
        if record is None:
            return

        workspace = workspace_at(state.checkout.toplevel)
        write_files(workspace.handoffs.snapshot(record.slug), record)


@dataclass(slots=True, kw_only=True, frozen=True)
class PreCompactHandler:
    environ: Mapping[str, str]
    stderr: TextIO

    async def handle(self, payload: PreCompactPayload) -> str | None:
        context = create_hook_context_at(self.environ, payload.cwd)
        if not context.has_ticket_directory():
            return None

        try:
            await write_snapshot(context)
        except UnknownRepositoryError:
            return None
        except STATE_UNREADABLE as error:
            self.stderr.write(f'mightymodels-hooks: pre-compact: {error}\n')

        return None
