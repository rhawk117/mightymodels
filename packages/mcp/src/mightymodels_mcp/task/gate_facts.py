"""The verification facts git and the workspace answer, gathered for core's `TaskService`.

Core takes values and never asks git or reads a file. A refusing git raises its refusal. A commit
that does not resolve is verified under the request's own text, so core words the failure. The base
is compared with the commit only when both resolve. Only a plan task has a brief, and the commit its
DONE section names counts only when git resolves it.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.tasks import Brief, GitFacts, VerifyRequest, done_commit, is_plan_task

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.git import Git
    from mightymodels_core.primitives import TaskId
    from mightymodels_core.tasks.records import TaskRecord
    from mightymodels_core.workspace import Workspace

    from mightymodels_mcp.task.schemas import TaskVerifyRequest


@dataclass(slots=True, kw_only=True, frozen=True)
class VerificationSources:
    git: Git
    workspace: Workspace


def read_brief(path: Path) -> Brief:
    try:
        return Brief(text=path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return Brief(text=None)


def brief_number(task_id: TaskId) -> int:
    return int(task_id[1:])


async def compare_with_base(
    git: Git, base: str | None, commit: str | None
) -> tuple[bool, frozenset[str]]:
    if base is None or commit is None:
        return False, frozenset[str]()

    return await git.is_ancestor(base, commit), frozenset(await git.changed_files(base, commit))


async def gather_verification(
    sources: VerificationSources, seen: TaskRecord, request: TaskVerifyRequest
) -> VerifyRequest:
    git = sources.git
    refusal = await git.refusal()
    if refusal is not None:
        raise refusal

    commit = await git.resolve_commit(request.commit)
    base = None if seen.base is None else await git.resolve_commit(seen.base)
    is_ancestor, changed_files = await compare_with_base(git, base, commit)
    brief = (
        read_brief(sources.workspace.task_brief(request.slug, brief_number(request.task_id)))
        if is_plan_task(request.task_id)
        else None
    )
    named = None if brief is None or brief.text is None else done_commit(brief.text)
    return VerifyRequest(
        seen=seen,
        commit=request.commit if commit is None else commit,
        assertions=request.assertions,
        git=GitFacts(
            head=await git.resolve_head(),
            base_resolves=base is not None,
            base_is_ancestor=is_ancestor,
            changed_files=changed_files,
            named_commit=None if named is None else await git.resolve_commit(named),
        ),
        brief=brief,
    )
