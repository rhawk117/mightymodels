"""The bounded git history a report reads: the window, the checks on its values and `git log`.

The target has to resolve inside the repository, to a path that is valid Unicode, before git is
launched. Each value then reaches git as one argument, the target after `--`. The launch goes
through the process runner under the git timeout. A target that is refused, a git that is missing
or does not answer, and a git that exits non-zero each surface as a `SignalsError`.
"""

import shutil
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from mightymodels_core.git import GIT_TIMEOUT_SECONDS
from mightymodels_core.primitives import StateError
from mightymodels_core.process import FailedRun, get_process_runner
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.process import ProcessRunner

    from .options import SignalsOptions

NUMSTAT_FIELDS = 3
RECORD = '\x1e'


class Analysis(StrEnum):
    CHURN = 'code-churn'
    COUPLING = 'change-coupling'
    HOTSPOTS = 'code-hotspots'


class SignalsError(StateError):
    pass


class NoRepositoryError(SignalsError):
    def __init__(self, *, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


class TargetOutsideError(SignalsError):
    def __init__(self, *, target: str) -> None:
        super().__init__(f'--target {target!r} is outside the repository')


class TargetNotUnicodeError(SignalsError):
    def __init__(self, *, path: str) -> None:
        super().__init__(f'--target resolves to {path!r}, which is not valid Unicode')


class GitMissingError(SignalsError):
    def __init__(self) -> None:
        super().__init__('git is not on PATH')


class GitFailedError(SignalsError):
    def __init__(self, *, detail: str) -> None:
        super().__init__(f'git log failed: {detail}')


@dataclass(slots=True, kw_only=True, frozen=True)
class GitSource:
    root: Path
    executable: str | None
    processes: ProcessRunner
    timeout: float = GIT_TIMEOUT_SECONDS


def create_git_source(root: Path) -> GitSource:
    return GitSource(root=root, executable=shutil.which('git'), processes=get_process_runner())


@dataclass(slots=True, kw_only=True, frozen=True)
class Window:
    since: str | None
    baseline_ref: str | None
    max_commits: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Commit:
    sha: str
    changes: dict[str, tuple[int, int]]


class ScannedHistory(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    since: str | None
    baseline_ref: str | None
    max_commits: int | None
    commits_scanned: int
    truncated: bool


class Report[Signal](BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    analysis: Analysis
    target: str
    history: ScannedHistory
    signals: list[Signal]
    limitations: list[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class History:
    root: Path
    target: str
    window: Window
    commits: list[Commit]

    @property
    def truncated(self) -> bool:
        limit = self.window.max_commits
        return limit is not None and len(self.commits) >= limit

    def report[Signal](
        self, analysis: Analysis, signals: list[Signal], limitations: list[str]
    ) -> Report[Signal]:
        return Report(
            analysis=analysis,
            target=self.target or '.',
            history=ScannedHistory(
                since=self.window.since,
                baseline_ref=self.window.baseline_ref,
                max_commits=self.window.max_commits,
                commits_scanned=len(self.commits),
                truncated=self.truncated,
            ),
            signals=signals,
            limitations=limitations,
        )

    def base_limitations(self) -> list[str]:
        notes = [
            (
                'merge commits are skipped; files deleted since are left out; '
                "a rename restarts a file's history"
            )
        ]
        if self.truncated:
            notes.append(
                f'history stopped at {self.window.max_commits} commits; '
                'widen with --max-commits or --all-history'
            )
        return notes


def repository_root(start: Path) -> Path:
    candidates = (start, *start.parents)
    root = next(
        (candidate for candidate in candidates if candidate.joinpath('.git').exists()), None
    )
    if root is None:
        raise NoRepositoryError(cwd=start)
    return root


def checked_target(root: Path, target: str | None) -> str:
    if target is None or target == '':
        return ''
    resolved = root.joinpath(target).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise TargetOutsideError(target=target)
    path = resolved.relative_to(root.resolve()).as_posix()
    try:
        path.encode()
    except UnicodeEncodeError as error:
        raise TargetNotUnicodeError(path=path) from error
    return path


def window_from(options: SignalsOptions) -> Window:
    limit = None if options.all_history else options.max_commits
    return Window(since=options.since, baseline_ref=options.baseline_ref, max_commits=limit)


def log_argv(git: str, target: str, window: Window) -> list[str]:
    argv = [git, 'log', '--no-merges', '--no-renames', '--numstat', '--format=%x1e%H']
    if window.max_commits is not None:
        argv.append(f'--max-count={window.max_commits}')
    if window.since is not None:
        argv.append(f'--since={window.since}')
    argv.append(f'{window.baseline_ref}..HEAD' if window.baseline_ref is not None else 'HEAD')
    argv.append('--')
    if target:
        argv.append(target)
    return argv


def count(text: str) -> int:
    return int(text) if text.isdigit() else 0


def parse_commit(block: str) -> Commit | None:
    lines = block.strip().splitlines()
    if not lines:
        return None
    rows = (line.split('\t') for line in lines[1:])
    changes = {
        path: (count(added), count(deleted))
        for added, deleted, path in (row for row in rows if len(row) == NUMSTAT_FIELDS)
    }
    return Commit(sha=lines[0].strip(), changes=changes)


def parse_log(output: str) -> list[Commit]:
    parsed = (parse_commit(block) for block in output.split(RECORD)[1:])
    return [commit for commit in parsed if commit is not None]


def without_deleted_files(root: Path, commit: Commit) -> Commit:
    present = {
        path: change for path, change in commit.changes.items() if root.joinpath(path).exists()
    }
    return replace(commit, changes=present)


async def load_history(options: SignalsOptions, git: GitSource) -> History:
    root = repository_root(git.root)
    if git.executable is None:
        raise GitMissingError
    target = checked_target(root, options.target)
    window = window_from(options)
    argv = log_argv(git.executable, target, window)
    run = await git.processes.run(argv, timeout=git.timeout, cwd=root)
    if isinstance(run, FailedRun):
        raise GitFailedError(detail=run.detail)
    if run.exit != 0:
        raise GitFailedError(detail=run.stderr.strip())
    commits = [without_deleted_files(root, commit) for commit in parse_log(run.stdout)]
    return History(root=root, target=target, window=window, commits=commits)
