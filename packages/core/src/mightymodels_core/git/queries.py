"""The seam under the workspace, edge and adapter layers: the questions asked of one checkout.

`refusal` and `checkout` answer with the error instead of raising it when git is missing, does
not answer, or the root is not in a repository. A revision or branch name that is not plain is
refused with `UnsafeRevisionError` before git is asked, and `is_ancestor` and `changed_files`
raise `GitUnavailableError` when git cannot answer for the commits named.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from .errors import GitRefusal
    from .records import Checkout, UntrackedFiles


@runtime_checkable
class Git(Protocol):
    async def refusal(self) -> GitRefusal | None: ...

    async def checkout(self) -> Checkout | GitRefusal: ...

    async def common_directory(self) -> Path | None: ...

    async def resolve_head(self) -> str | None: ...

    async def resolve_commit(self, revision: str) -> str | None: ...

    async def is_ancestor(self, base: str, commit: str) -> bool: ...

    async def changed_files(self, base: str, commit: str) -> set[str]: ...

    async def current_branch(self) -> str | None: ...

    async def dirty_paths(self, *, untracked: UntrackedFiles) -> list[str] | None: ...

    async def commits_on_no_remote(self, branch: str) -> int | None: ...
