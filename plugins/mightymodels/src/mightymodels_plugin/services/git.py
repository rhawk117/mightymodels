"""The git questions the services ask, each a fixed argv run without a shell."""

import re
import subprocess
from pathlib import Path

from mightymodels_plugin.errors import StateError

SAFE_REVISION = re.compile(r'^[0-9A-Za-z][0-9A-Za-z._/-]*$')


class UnsafeRevisionError(StateError):
    def __init__(self, revision: str) -> None:
        super().__init__(f'{revision!r} is not a plain revision name')
        self.revision = revision


class GitUnavailableError(StateError):
    def __init__(self, detail: str) -> None:
        super().__init__(f'git could not list the commit changes: {detail}')
        self.detail = detail


def git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed git argv, every argument is a separate word and revisions are checked plain names
        ['git', '-C', str(root), *arguments],  # noqa: S607 - git is resolved from PATH like every other tool the plugin runs
        capture_output=True,
        text=True,
        check=False,
    )


def safe_revision(revision: str) -> str:
    if not SAFE_REVISION.match(revision):
        raise UnsafeRevisionError(revision)
    return revision


def resolve_head(root: Path) -> str | None:
    completed = git(root, 'rev-parse', '--verify', '--quiet', 'HEAD')
    return completed.stdout.strip() if completed.returncode == 0 else None


def resolve_commit(root: Path, revision: str) -> str | None:
    completed = git(
        root, 'rev-parse', '--verify', '--quiet', f'{safe_revision(revision)}^{{commit}}'
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def is_ancestor(root: Path, base: str, commit: str) -> bool:
    completed = git(root, 'merge-base', '--is-ancestor', safe_revision(base), safe_revision(commit))
    if completed.returncode > 1:
        raise GitUnavailableError(completed.stderr.strip())
    return completed.returncode == 0


def changed_files(root: Path, base: str, commit: str) -> set[str]:
    revisions = f'{safe_revision(base)}..{safe_revision(commit)}'
    completed = git(root, 'diff', '--name-only', revisions, '--')
    if completed.returncode != 0:
        raise GitUnavailableError(completed.stderr.strip())
    return {line for line in completed.stdout.splitlines() if line}
