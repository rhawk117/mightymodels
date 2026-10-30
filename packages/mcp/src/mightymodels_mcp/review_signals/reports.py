"""The three analyses over a loaded history, and the signal each one ranks."""

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from .schemas import Analysis

if TYPE_CHECKING:
    from pathlib import Path

    from .history import History
    from .schemas import ChangeCouplingRequest, HistoryWindowRequest, Report

INDENT_WIDTH = 4
TAB_WIDTH = 4
MAX_FILE_BYTES = 2_000_000
BINARY_SNIFF = 8192


@dataclass(slots=True, kw_only=True, frozen=True)
class Churn:
    commits: int = 0
    added: int = 0
    deleted: int = 0


def churn_by_file(history: History) -> dict[str, Churn]:
    totals: dict[str, Churn] = {}
    for commit in history.commits:
        for path, (added, deleted) in commit.changes.items():
            before = totals.get(path, Churn())
            totals[path] = Churn(
                commits=before.commits + 1,
                added=before.added + added,
                deleted=before.deleted + deleted,
            )
    return totals


def churn_order(item: tuple[str, Churn]) -> tuple[int, int, str]:
    path, churn = item
    return -churn.commits, -(churn.added + churn.deleted), path


class ChurnSignal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    subject: str
    commits: int
    lines_added: int
    lines_deleted: int


def code_churn(history: History, options: HistoryWindowRequest) -> Report[ChurnSignal]:
    ranked = sorted(churn_by_file(history).items(), key=churn_order)
    signals = [
        ChurnSignal(
            subject=path,
            commits=churn.commits,
            lines_added=churn.added,
            lines_deleted=churn.deleted,
        )
        for path, churn in ranked[: options.limit]
    ]
    limitations = history.base_limitations()
    limitations.append('binary files count commits but no lines')
    return history.report(Analysis.CHURN, signals, limitations)


class CouplingSignal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    subject: str
    shared_commits: int
    degree: float


def coupling_order(pair: CouplingSignal) -> tuple[int, float, str]:
    return -pair.shared_commits, -pair.degree, pair.subject


def ranked_pairs(
    shared: Counter[tuple[str, str]], revisions: Counter[str], min_shared: int
) -> list[CouplingSignal]:
    pairs = [
        CouplingSignal(
            subject=f'{left} <-> {right}',
            shared_commits=together,
            degree=round(together / min(revisions[left], revisions[right]), 2),
        )
        for (left, right), together in shared.items()
        if together >= min_shared
    ]
    return sorted(pairs, key=coupling_order)


def coupling_pairs(
    history: History, options: ChangeCouplingRequest
) -> tuple[list[CouplingSignal], int]:
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
    pairs = ranked_pairs(shared, revisions, options.min_shared)
    return pairs, skipped


def coupling_limitations(
    history: History, options: ChangeCouplingRequest, skipped: int
) -> list[str]:
    limitations = history.base_limitations()
    limitations.append('degree is shared commits divided by the less-changed file')
    if skipped:
        limitations.append(
            f'{skipped} commits touching more than {options.max_changeset} files '
            'were left out of pairing'
        )
    return limitations


def change_coupling(history: History, options: ChangeCouplingRequest) -> Report[CouplingSignal]:
    pairs, skipped = coupling_pairs(history, options)
    limitations = coupling_limitations(history, options, skipped)
    return history.report(Analysis.COUPLING, pairs[: options.limit], limitations)


@dataclass(slots=True, kw_only=True, frozen=True)
class Shape:
    loc: int
    indentation: int


def indent_level(line: str) -> int:
    stripped = line.lstrip(' \t')
    width = len(line[: len(line) - len(stripped)].expandtabs(TAB_WIDTH))
    return width // INDENT_WIDTH


def shape_of(path: Path) -> Shape | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return None

        raw = path.read_bytes()
    except OSError:
        return None

    if b'\0' in raw[:BINARY_SNIFF]:
        return None
    lines = [line for line in raw.decode('utf-8', 'replace').splitlines() if line.strip()]
    return Shape(loc=len(lines), indentation=sum(map(indent_level, lines)))


class HotspotSignal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    subject: str
    commits: int
    loc: int
    indentation: int
    hotspot: int


def hotspot_order(signal: HotspotSignal) -> tuple[int, str]:
    return -signal.hotspot, signal.subject


def hotspot_signal(path: str, churn: Churn, root: Path) -> HotspotSignal | None:
    shape = shape_of(root.joinpath(path))
    if shape is None:
        return None
    return HotspotSignal(
        subject=path,
        commits=churn.commits,
        loc=shape.loc,
        indentation=shape.indentation,
        hotspot=churn.commits * shape.indentation,
    )


def code_hotspots(history: History, options: HistoryWindowRequest) -> Report[HotspotSignal]:
    measured = (
        hotspot_signal(path, churn, history.root) for path, churn in churn_by_file(history).items()
    )
    signals = sorted((signal for signal in measured if signal is not None), key=hotspot_order)
    limitations = history.base_limitations()
    limitations.extend([
        (
            'hotspot is commits times indentation complexity (indent levels summed '
            'over non-blank lines), measured on the working tree'
        ),
        'binary files, files over 2 MB and unreadable files are skipped',
    ])
    return history.report(Analysis.HOTSPOTS, signals[: options.limit], limitations)
