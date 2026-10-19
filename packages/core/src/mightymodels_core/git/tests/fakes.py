"""A git history kept in memory and a process runner that records what it was asked.

`InMemoryGit` answers every `Git` operation as `ProcessGit` does for the same repository
state. `commit` records the files a commit changed on top of HEAD and moves HEAD to it, or
starts an unrelated history. A revision names HEAD, a branch in `branches` or the start of one
commit's sha, and a name that is none of them is unknown. `ProcessGit` reports an unknown
commit to `is_ancestor` and `changed_files` as `GitUnavailableError`, and so does this fake.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from mightymodels_core.git.errors import GitUnavailableError
from mightymodels_core.git.records import Checkout, UntrackedFiles
from mightymodels_core.git.revisions import revision_error
from mightymodels_core.process import CompletedRun

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    from mightymodels_core.git.errors import GitRefusal
    from mightymodels_core.process import RunOutcome

HEAD = 'HEAD'
BRANCH_REFS = 'refs/heads/'
SHA_LENGTH = 40
UNKNOWN_REVISION = 'unknown revision'
ANSWERED = CompletedRun(exit=0, stdout='0\n', stderr='')


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedCommit:
    sha: str
    parent: str | None
    changed: frozenset[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class CommitHistory:
    branches: Collection[str] = ()
    commits: list[RecordedCommit] = field(default_factory=list)

    def commit(self, *changed: str, unrelated: bool = False) -> str:
        sha = hashlib.sha256(str(len(self.commits)).encode()).hexdigest()[:SHA_LENGTH]
        parent = None if unrelated or not self.commits else self.commits[-1].sha
        self.commits.append(RecordedCommit(sha=sha, parent=parent, changed=frozenset(changed)))
        return sha

    def head(self) -> str | None:
        return self.commits[-1].sha if self.commits else None

    def reached_from(self, sha: str) -> list[RecordedCommit]:
        held = {commit.sha: commit for commit in self.commits}
        reached: list[RecordedCommit] = []
        current = held.get(sha)
        while current is not None:
            reached.append(current)
            current = None if current.parent is None else held.get(current.parent)
        return reached

    def named(self, revision: str) -> str | None:
        if revision == HEAD or revision.removeprefix(BRANCH_REFS) in self.branches:
            return self.head()

        starting = {commit.sha for commit in self.commits if commit.sha.startswith(revision)}
        return starting.pop() if len(starting) == 1 else None

    def known(self, revision: str) -> str:
        sha = self.named(revision)
        if sha is None:
            raise GitUnavailableError(detail=UNKNOWN_REVISION)

        return sha


@dataclass(slots=True, kw_only=True, frozen=True)
class InMemoryGit:
    history: CommitHistory = field(default_factory=CommitHistory)
    branch: str | None = 'main'
    refused: GitRefusal | None = None
    checkout_at: Checkout = field(
        default_factory=lambda: Checkout(toplevel=Path('/repository'), origin_url=None)
    )
    common: Path | None = None
    dirty: Sequence[str] | None = ()
    untracked: Sequence[str] = ()
    unpushed: Mapping[str, int] = field(default_factory=dict)

    async def refusal(self) -> GitRefusal | None:
        return self.refused

    async def checkout(self) -> Checkout | GitRefusal:
        return self.refused or self.checkout_at

    async def common_directory(self) -> Path | None:
        return self.common

    async def resolve_head(self) -> str | None:
        return self.history.head()

    async def resolve_commit(self, revision: str) -> str | None:
        if (error := revision_error(revision)) is not None:
            raise error

        return self.history.named(revision)

    async def is_ancestor(self, base: str, commit: str) -> bool:
        if (error := revision_error(base, commit)) is not None:
            raise error

        reached = self.history.reached_from(self.history.known(commit))
        return self.history.known(base) in {step.sha for step in reached}

    async def changed_files(self, base: str, commit: str) -> set[str]:
        if (error := revision_error(base, commit)) is not None:
            raise error

        behind = {step.sha for step in self.history.reached_from(self.history.known(base))}
        reached = self.history.reached_from(self.history.known(commit))
        since = (step for step in reached if step.sha not in behind)
        return {path for step in since for path in step.changed}

    async def current_branch(self) -> str | None:
        return self.branch

    async def dirty_paths(self, *, untracked: UntrackedFiles) -> list[str] | None:
        if self.dirty is None:
            return None

        shown = self.untracked if untracked is UntrackedFiles.NORMAL else ()
        return [*self.dirty, *shown]

    async def commits_on_no_remote(self, branch: str) -> int | None:
        if (error := revision_error(branch)) is not None:
            raise error

        return self.unpushed.get(branch)


@dataclass(slots=True, kw_only=True, frozen=True)
class RecordedRun:
    argv: tuple[str, ...]
    timeout: float
    cwd: Path | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ScriptedRunner:
    reply: RunOutcome = ANSWERED
    runs: list[RecordedRun] = field(default_factory=list)

    async def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,  # noqa: ASYNC109  the ProcessRunner Protocol fixes this signature; the fake records the timeout, never enforces it
        cwd: Path | None = None,
    ) -> RunOutcome:
        recorded = RecordedRun(argv=tuple(argv), timeout=timeout, cwd=cwd)
        self.runs.append(recorded)
        return self.reply
