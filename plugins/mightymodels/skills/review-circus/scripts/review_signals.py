"""Git-history risk signals for review-circus and qualitylens: churn, coupling, hotspots.

Every analysis reads `git log` for a bounded history window and prints one JSON document:
the analysis, the target, the window actually scanned, the signals, and the limitations
that apply. Nothing is interpreted; a high value is evidence for a reviewer to weigh.
Dependency structure (fan-in, fan-out, cycles) is metrics.py's job, not this script's.

Usage:
    python3 review_signals.py code-churn [--target PATH] [WINDOW] [--limit N]
    python3 review_signals.py change-coupling [--target PATH] [WINDOW] [--min-shared N]
        [--max-changeset N] [--limit N]
    python3 review_signals.py code-hotspots [--target PATH] [WINDOW] [--limit N]

WINDOW is any of --since DATE, --baseline-ref REF, and --max-commits N or --all-history.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

EXIT_REJECTED = 2
DEFAULT_MAX_COMMITS = 500
DEFAULT_LIMIT = 25
DEFAULT_MIN_SHARED = 3
DEFAULT_MAX_CHANGESET = 50
INDENT_WIDTH = 4
TAB_WIDTH = 4
MAX_FILE_BYTES = 2_000_000
BINARY_SNIFF = 8192
NUMSTAT_FIELDS = 3
RECORD = '\x1e'
SAFE_REVISION = re.compile(r'^[0-9A-Za-z][0-9A-Za-z._/-]*$')
SAFE_SINCE = re.compile(r'^[0-9A-Za-z][0-9A-Za-z .:+-]*$')


class Analysis(StrEnum):
    CHURN = 'code-churn'
    COUPLING = 'change-coupling'
    HOTSPOTS = 'code-hotspots'


class SignalsError(Exception):
    pass


class NoRepositoryError(SignalsError):
    def __init__(self, cwd: Path) -> None:
        super().__init__(f'{cwd} is not inside a git repository')


class UnsafeValueError(SignalsError):
    def __init__(self, flag: str, value: str) -> None:
        super().__init__(f'{flag} {value!r} is not a plain value')


class TargetOutsideError(SignalsError):
    def __init__(self, target: str) -> None:
        super().__init__(f'--target {target!r} is outside the repository')


class GitMissingError(SignalsError):
    def __init__(self) -> None:
        super().__init__('git is not on PATH')


class GitFailedError(SignalsError):
    def __init__(self, detail: str) -> None:
        super().__init__(f'git log failed: {detail}')


@dataclass(frozen=True, slots=True)
class Window:
    since: str | None
    baseline_ref: str | None
    max_commits: int | None


@dataclass(slots=True)
class Commit:
    sha: str
    changes: dict[str, tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class History:
    root: Path
    target: str
    window: Window
    commits: list[Commit]

    @property
    def truncated(self) -> bool:
        limit = self.window.max_commits
        return limit is not None and len(self.commits) >= limit

    def header(self, analysis: Analysis) -> dict[str, object]:
        return {
            'analysis': str(analysis),
            'target': self.target or '.',
            'history': {
                'since': self.window.since,
                'baseline_ref': self.window.baseline_ref,
                'max_commits': self.window.max_commits,
                'commits_scanned': len(self.commits),
                'truncated': self.truncated,
            },
        }

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
    for candidate in (start, *start.parents):
        if (candidate / '.git').exists():
            return candidate
    raise NoRepositoryError(start)


def checked(flag: str, value: str | None, pattern: re.Pattern[str]) -> str | None:
    if value is not None and not pattern.match(value):
        raise UnsafeValueError(flag, value)
    return value


def checked_target(root: Path, target: str | None) -> str:
    if not target:
        return ''
    resolved = (root / target).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise TargetOutsideError(target)
    return resolved.relative_to(root.resolve()).as_posix()


def window_from(options: argparse.Namespace) -> Window:
    limit = None if options.all_history else options.max_commits
    return Window(
        since=checked('--since', options.since, SAFE_SINCE),
        baseline_ref=checked('--baseline-ref', options.baseline_ref, SAFE_REVISION),
        max_commits=limit,
    )


def log_argv(git: str, target: str, window: Window) -> list[str]:
    argv = [git, 'log', '--no-merges', '--no-renames', '--numstat', '--format=%x1e%H']
    if window.max_commits is not None:
        argv.append(f'--max-count={window.max_commits}')
    if window.since is not None:
        argv.append(f'--since={window.since}')
    argv.append(f'{window.baseline_ref}..HEAD' if window.baseline_ref else 'HEAD')
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
    commit = Commit(sha=lines[0].strip())
    rows = (line.split('\t') for line in lines[1:])
    for added, deleted, path in (row for row in rows if len(row) == NUMSTAT_FIELDS):
        commit.changes[path] = (count(added), count(deleted))
    return commit


def parse_log(output: str) -> list[Commit]:
    parsed = (parse_commit(block) for block in output.split(RECORD)[1:])
    return [commit for commit in parsed if commit is not None]


def load_history(options: argparse.Namespace) -> History:
    root = repository_root(Path.cwd())
    git = shutil.which('git')
    if git is None:
        raise GitMissingError
    target = checked_target(root, options.target)
    window = window_from(options)
    completed = subprocess.run(  # noqa: S603 - fixed git argv; revision and date are validated, the target follows --
        log_argv(git, target, window),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GitFailedError(completed.stderr.strip())
    commits = parse_log(completed.stdout)
    for commit in commits:
        commit.changes = {
            path: change for path, change in commit.changes.items() if (root / path).exists()
        }
    return History(root, target, window, commits)


@dataclass(slots=True)
class Churn:
    commits: int = 0
    added: int = 0
    deleted: int = 0


def churn_by_file(history: History) -> dict[str, Churn]:
    totals: dict[str, Churn] = {}
    for commit in history.commits:
        for path, (added, deleted) in commit.changes.items():
            entry = totals.setdefault(path, Churn())
            entry.commits += 1
            entry.added += added
            entry.deleted += deleted
    return totals


def churn_order(item: tuple[str, Churn]) -> tuple[int, int, str]:
    path, churn = item
    return -churn.commits, -(churn.added + churn.deleted), path


def code_churn(history: History, options: argparse.Namespace) -> dict[str, object]:
    ranked = sorted(churn_by_file(history).items(), key=churn_order)
    signals = [
        {
            'subject': path,
            'commits': churn.commits,
            'lines_added': churn.added,
            'lines_deleted': churn.deleted,
        }
        for path, churn in ranked[: options.limit]
    ]
    limitations = history.base_limitations()
    limitations.append('binary files count commits but no lines')
    return {
        **history.header(Analysis.CHURN),
        'signals': signals,
        'limitations': limitations,
    }


def change_coupling(history: History, options: argparse.Namespace) -> dict[str, object]:
    revisions: Counter[str] = Counter()
    shared: Counter[tuple[str, str]] = Counter()
    skipped = 0
    for commit in history.commits:
        paths = sorted(commit.changes)
        revisions.update(paths)
        if len(paths) > options.max_changeset:
            skipped += 1
            continue
        shared.update(combinations(paths, 2))
    pairs: list[dict[str, object]] = [
        {
            'subject': f'{left} <-> {right}',
            'shared_commits': together,
            'degree': round(together / min(revisions[left], revisions[right]), 2),
        }
        for (left, right), together in shared.items()
        if together >= options.min_shared
    ]
    pairs.sort(key=coupling_order)
    limitations = history.base_limitations()
    limitations.append('degree is shared commits divided by the less-changed file')
    if skipped:
        limitations.append(
            f'{skipped} commits touching more than {options.max_changeset} files '
            'were left out of pairing'
        )
    header = history.header(Analysis.COUPLING)
    return {**header, 'signals': pairs[: options.limit], 'limitations': limitations}


def coupling_order(pair: dict[str, object]) -> tuple[int, float, str]:
    return (
        -int(str(pair['shared_commits'])),
        -float(str(pair['degree'])),
        str(pair['subject']),
    )


@dataclass(frozen=True, slots=True)
class Shape:
    loc: int
    indentation: int


def indent_level(line: str) -> int:
    stripped = line.lstrip(' \t')
    width = len(line[: len(line) - len(stripped)].expandtabs(TAB_WIDTH))
    return width // INDENT_WIDTH


def shape_of(path: Path) -> Shape | None:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        return None
    raw = path.read_bytes()
    if b'\0' in raw[:BINARY_SNIFF]:
        return None
    lines = [line for line in raw.decode('utf-8', 'replace').splitlines() if line.strip()]
    return Shape(loc=len(lines), indentation=sum(map(indent_level, lines)))


def hotspot_order(signal: dict[str, object]) -> tuple[int, str]:
    return -int(str(signal['hotspot'])), str(signal['subject'])


def code_hotspots(history: History, options: argparse.Namespace) -> dict[str, object]:
    signals: list[dict[str, object]] = []
    for path, churn in churn_by_file(history).items():
        shape = shape_of(history.root / path)
        if shape is None:
            continue
        signals.append(
            {
                'subject': path,
                'commits': churn.commits,
                'loc': shape.loc,
                'indentation': shape.indentation,
                'hotspot': churn.commits * shape.indentation,
            }
        )
    signals.sort(key=hotspot_order)
    limitations = history.base_limitations()
    limitations.extend(
        [
            (
                'hotspot is commits times indentation complexity (indent levels summed '
                'over non-blank lines), measured on the working tree'
            ),
            'binary files and files over 2 MB are skipped',
        ]
    )
    header = history.header(Analysis.HOTSPOTS)
    return {**header, 'signals': signals[: options.limit], 'limitations': limitations}


HANDLERS: dict[Analysis, Callable[[History, argparse.Namespace], dict[str, object]]] = {
    Analysis.CHURN: code_churn,
    Analysis.COUPLING: change_coupling,
    Analysis.HOTSPOTS: code_hotspots,
}


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        message = 'must be at least 1'
        raise argparse.ArgumentTypeError(message)
    return value


def add_window(sub: argparse.ArgumentParser) -> None:
    sub.add_argument('--target', help='file or directory, relative to the repository')
    sub.add_argument('--since', help='git date, e.g. 2026-01-01 or "6 months ago"')
    sub.add_argument('--baseline-ref', help='only commits after this ref, up to HEAD')
    size = sub.add_mutually_exclusive_group()
    size.add_argument('--max-commits', type=positive, default=DEFAULT_MAX_COMMITS)
    size.add_argument('--all-history', action='store_true')
    sub.add_argument('--limit', type=positive, default=DEFAULT_LIMIT)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='review_signals.py', description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest='analysis', required=True)
    churn = commands.add_parser(Analysis.CHURN, help='commits and lines changed per file')
    coupling = commands.add_parser(Analysis.COUPLING, help='files that change in the same commits')
    coupling.add_argument('--min-shared', type=positive, default=DEFAULT_MIN_SHARED)
    coupling.add_argument('--max-changeset', type=positive, default=DEFAULT_MAX_CHANGESET)
    hotspots = commands.add_parser(
        Analysis.HOTSPOTS, help='churn weighted by indentation complexity'
    )
    for sub in (churn, coupling, hotspots):
        add_window(sub)
    return root


def main(argv: list[str] | None = None) -> int:
    options = parser().parse_args(argv)
    try:
        history = load_history(options)
    except SignalsError as error:
        sys.stderr.write(f'error: {error}\n')
        return EXIT_REJECTED
    report = HANDLERS[Analysis(options.analysis)](history, options)
    sys.stdout.write(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
