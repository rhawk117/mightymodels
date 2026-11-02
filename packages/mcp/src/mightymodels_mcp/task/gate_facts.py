"""The verification facts git answers, gathered for core's `TaskService`.

Core takes values and never asks git. A refusing git raises its refusal. A commit that does not
resolve is recorded under the request's own text. The base is compared with the commit only when
both resolve. None of the facts changes the verdict the request carries.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.tasks import GitFacts, VerifyRequest

if TYPE_CHECKING:
    from mightymodels_core.git import Git
    from mightymodels_core.tasks.records import TaskRecord

    from mightymodels_mcp.task.schemas import TaskVerifyRequest


@dataclass(slots=True, kw_only=True, frozen=True)
class VerificationSources:
    git: Git


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


async def gather_git_facts(git: Git, comparison: BaseComparison) -> GitFacts:
    return GitFacts(
        head=await git.resolve_head(),
        base_resolves=comparison.resolves,
        base_is_ancestor=comparison.is_ancestor,
        changed_files=comparison.changed_files,
    )


async def gather_verification(
    sources: VerificationSources, seen: TaskRecord, request: TaskVerifyRequest
) -> VerifyRequest:
    git = sources.git
    refusal = await git.refusal()
    if refusal is not None:
        raise refusal

    commit = await git.resolve_commit(request.commit)
    comparison = await compare_with_base(git, seen.base, commit)
    return VerifyRequest(
        seen=seen,
        commit=commit or request.commit,
        verdict=request.verdict,
        reason=request.reason,
        git=await gather_git_facts(git, comparison),
    )
