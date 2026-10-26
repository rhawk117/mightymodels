"""The journal use cases: sync functions, each opening one `JournalWork` unit.

A unit holds the database connection synchronously and must never be held across an `await`. No
journal tool asks git, because core takes no HEAD. Add opens a write unit; stats, last and search
open a read unit.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.units_of_work import JournalWork

from mightymodels_mcp.server.state import create_work

from .views import render_journaled, render_last, render_matches, render_stats

if TYPE_CHECKING:
    from mightymodels_core.crashouts import CrashoutEntry
    from mightymodels_core.edge import OpenState
    from mightymodels_core.vocabulary.similarity import SimilarityKind

    from .views import JournalView


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityQuery:
    query: str
    kind: SimilarityKind | None


def create_journal_work(state: OpenState) -> JournalWork:
    return create_work(state, JournalWork)


def add_crashout(work: JournalWork, entry: CrashoutEntry) -> JournalView:
    with work.write() as unit:
        journaled = unit.crashouts.add(entry)

    return render_journaled(journaled)


def show_crashout_stats(work: JournalWork) -> JournalView:
    with work.read() as unit:
        stats = unit.crashouts.stats()

    return render_stats(stats)


def show_last_crashout(work: JournalWork) -> JournalView:
    with work.read() as unit:
        record = unit.crashouts.last()

    return render_last(record)


def search_similar(work: JournalWork, asked: SimilarityQuery) -> JournalView:
    with work.read() as unit:
        matches = unit.similarity.search(asked.query, asked.kind)

    return render_matches(matches)
