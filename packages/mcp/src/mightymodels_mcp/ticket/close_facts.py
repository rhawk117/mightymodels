"""The close facts git and the workspace answer, gathered for core's `ClosingService`.

Core takes values and never asks git. `prepare` reads the ticket and the workspace says whether the
debug note is live; the rest is asked of git here, between the two units a close runs as. A branch
whose name is not a safe revision is never given to git, and it comes back as no branch facts so
core words it as unchecked. Git facts left unasked by a refusal are empty.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.git import UntrackedFiles
from mightymodels_core.git.revisions import revision_error
from mightymodels_core.ticket_closing.records import BranchFacts, CloseFacts

if TYPE_CHECKING:
    from mightymodels_core.git import Git
    from mightymodels_core.primitives import Slug
    from mightymodels_core.ticket_closing.records import ClosingLines
    from mightymodels_core.tickets.records import TicketRecord


@dataclass(slots=True, kw_only=True, frozen=True)
class PreparedClose:
    seen: TicketRecord
    debug_note: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseAttempt:
    slug: Slug
    prepared: PreparedClose
    facts: CloseFacts
    lines: ClosingLines


async def count_dirty_paths(git: Git) -> int | None:
    paths = await git.dirty_paths(untracked=UntrackedFiles.NO)
    return None if paths is None else len(paths)


async def gather_branch_facts(git: Git, branch: str) -> BranchFacts | None:
    if revision_error(branch) is not None:
        return None

    if await git.resolve_commit(f'refs/heads/{branch}') is None:
        return BranchFacts(exists=False, unpushed=None, checked_out=False, dirty=None)

    checked_out = await git.current_branch() == branch
    return BranchFacts(
        exists=True,
        unpushed=await git.commits_on_no_remote(branch),
        checked_out=checked_out,
        dirty=await count_dirty_paths(git) if checked_out else None,
    )


async def gather_close_facts(git: Git, prepared: PreparedClose) -> CloseFacts:
    refusal = await git.refusal()
    if refusal is not None:
        return CloseFacts(
            debug_note=prepared.debug_note, git_refusal=str(refusal), head=None, branch=None
        )

    return CloseFacts(
        debug_note=prepared.debug_note,
        git_refusal=None,
        head=await git.resolve_head(),
        branch=await gather_branch_facts(git, prepared.seen.section.branch),
    )
