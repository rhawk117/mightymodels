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


@dataclass(slots=True, kw_only=True, frozen=True)
class BaseComparison:
    resolves: bool
    is_ancestor: bool
    changed_files: frozenset[str]


async def compare_with_base(git: Git, seen_base: str | None, commit: str | None) -> BaseComparison:
    base = None if seen_base is None else await git.resolve_commit(seen_base)
    if base is None or commit is None:
        return BaseComparison(
            resolves=base is not None, is_ancestor=False, changed_files=frozenset()
        )

    return BaseComparison(
        resolves=True,
        is_ancestor=await git.is_ancestor(base, commit),
        changed_files=frozenset(await git.changed_files(base, commit)),
    )


async def load_brief(sources: VerificationSources, request: TaskVerifyRequest) -> Brief | None:
    if not is_plan_task(request.task_id):
        return None

    return read_brief(sources.workspace.task_brief(request.slug, brief_number(request.task_id)))


async def resolve_named_commit(git: Git, brief: Brief | None) -> str | None:
    if brief is None or brief.text is None:
        return None

    named = done_commit(brief.text)
    if named is None:
        return None

    return await git.resolve_commit(named)


async def gather_git_facts(git: Git, comparison: BaseComparison, brief: Brief | None) -> GitFacts:
    return GitFacts(
        head=await git.resolve_head(),
        base_resolves=comparison.resolves,
        base_is_ancestor=comparison.is_ancestor,
        changed_files=comparison.changed_files,
        named_commit=await resolve_named_commit(git, brief),
    )


async def gather_verification(
    sources: VerificationSources, seen: TaskRecord, request: TaskVerifyRequest
) -> VerifyRequest:
    git = sources.git
    refusal = await git.refusal()
    if refusal is not None:
        raise refusal

    commit = await git.resolve_commit(request.commit)
    brief = await load_brief(sources, request)
    comparison = await compare_with_base(git, seen.base, commit)
    return VerifyRequest(
        seen=seen,
        commit=commit or request.commit,
        assertions=request.assertions,
        git=await gather_git_facts(git, comparison, brief),
        brief=brief,
    )
