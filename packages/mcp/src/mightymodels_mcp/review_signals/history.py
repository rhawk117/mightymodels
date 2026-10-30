"""The bounded git history a report reads: the window, the checks on its values and `git log`.

The target has to resolve inside the repository, to a path that is valid Unicode, before git is
launched. Each value then reaches git as one argument, the target after `--`. The launch goes
through the process runner under the git timeout. A target that is refused, a git that is missing
or does not answer, and a git that exits non-zero each surface as a `SignalsError`.
"""

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from anyio import to_thread

from .errors import (
    GitFailedError,
    GitMissingError,
    TargetNotUnicodeError,
    TargetOutsideError,
)
from .schemas import Report, ScannedHistory

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.git import GitCommand

    from .schemas import Analysis, HistoryWindowRequest

NUMSTAT_FIELDS = 3
OCTAL_DIGITS = 3
RECORD = '\x1e'
QUOTE = '"'
QUOTED_ESCAPE = re.compile(rb'\\([0-7]{3}|.)', re.DOTALL)
SIMPLE_ESCAPES: dict[bytes, bytes] = {
    b'a': b'\a',
    b'b': b'\b',
    b'f': b'\f',
    b'n': b'\n',
    b'r': b'\r',
    b't': b'\t',
    b'v': b'\v',
}


@dataclass(slots=True, kw_only=True, frozen=True)
class Window:
    since: str | None
    baseline_ref: str | None
    max_commits: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Commit:
    sha: str
    changes: dict[str, tuple[int, int]]
    dropped: int = 0


@dataclass(slots=True, kw_only=True, frozen=True)
class History:
    root: Path
    target: str
    window: Window
    commits: list[Commit]

    @property
    def dropped_names(self) -> int:
        return sum(commit.dropped for commit in self.commits)

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
        if self.dropped_names:
            notes.append(
                f'{self.dropped_names} changed paths whose names are not valid UTF-8 were left out'
            )
        return notes


def checked_target(root: Path, target: str | None) -> str:
    if target is None or target == '':
        return ''
    try:
        resolved = root.joinpath(target).resolve()
    except ValueError as error:
        raise TargetOutsideError(target=target) from error

    if not resolved.is_relative_to(root.resolve()):
        raise TargetOutsideError(target=target)
    path = resolved.relative_to(root.resolve()).as_posix()
    try:
        path.encode()
    except UnicodeEncodeError as error:
        raise TargetNotUnicodeError(path=path) from error
    return path


def window_from(options: HistoryWindowRequest) -> Window:
    limit = None if options.all_history else options.max_commits
    return Window(since=options.since, baseline_ref=options.baseline_ref, max_commits=limit)


def log_argv(target: str, window: Window) -> list[str]:
    argv = [
        '--literal-pathspecs',
        'log',
        '--no-merges',
        '--no-renames',
        '--numstat',
        '--format=%x1e%H',
    ]
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


def unescape(match: re.Match[bytes]) -> bytes:
    code = bytes(match.group(1))
    if len(code) == OCTAL_DIGITS:
        return bytes([int(code, 8) & 0xFF])

    return SIMPLE_ESCAPES.get(code, code)


def unquote(path: str) -> str | None:
    if not (path.startswith(QUOTE) and path.endswith(QUOTE)):
        return path

    raw = QUOTED_ESCAPE.sub(unescape, path[1:-1].encode())
    try:
        return raw.decode()
    except UnicodeDecodeError:
        return None


def parse_commit(block: str) -> Commit | None:
    lines = block.strip().splitlines()
    if not lines:
        return None

    rows = (line.split('\t') for line in lines[1:])
    fields = [row for row in rows if len(row) == NUMSTAT_FIELDS]
    named = [(added, deleted, unquote(path)) for added, deleted, path in fields]
    changes = {
        path: (count(added), count(deleted)) for added, deleted, path in named if path is not None
    }
    return Commit(sha=lines[0].strip(), changes=changes, dropped=len(fields) - len(changes))


def parse_log(output: str) -> list[Commit]:
    parsed = (parse_commit(block) for block in output.split(RECORD)[1:])
    return [commit for commit in parsed if commit is not None]


def without_deleted_files(root: Path, commit: Commit) -> Commit:
    present = {
        path: change for path, change in commit.changes.items() if root.joinpath(path).exists()
    }
    return replace(commit, changes=present)


@dataclass(slots=True, kw_only=True, frozen=True)
class Located:
    root: Path
    target: str


def locate_target(root: Path, options: HistoryWindowRequest) -> Located:
    return Located(root=root, target=checked_target(root, options.target))


def history_from_output(located: Located, window: Window, stdout: str) -> History:
    commits = [without_deleted_files(located.root, commit) for commit in parse_log(stdout)]
    return History(root=located.root, target=located.target, window=window, commits=commits)


async def load_history(options: HistoryWindowRequest, command: GitCommand) -> History:
    if command.executable is None:
        raise GitMissingError

    located = await to_thread.run_sync(locate_target, command.root, options)
    window = window_from(options)
    answer = await command.answer(*log_argv(located.target, window))
    if answer.failure is not None or answer.exit != 0:
        raise GitFailedError(detail=answer.stderr.strip())

    return await to_thread.run_sync(history_from_output, located, window, answer.stdout)
