"""The crashout service: an append-only journal of crashouts.

It takes values and returns values: the crashout number and the duplicates of its root cause, the
patterns of the latest crashouts, the newest crashout. The caller wraps a call in its unit of work
and words the response. `add` stamps the crashout with the time the clock gives and sends the root
cause to the similarity repository under the crashout number.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.crashouts.policy import CrashoutOptions, CrashoutPolicy
from mightymodels_core.similarity.records import Written

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import date

    from mightymodels_core.crashouts.policy import CrashoutEntry
    from mightymodels_core.crashouts.records import CrashoutRecord
    from mightymodels_core.crashouts.repository import CrashoutRepository
    from mightymodels_core.primitives import Clock, RedactedText
    from mightymodels_core.schemas.crashouts import CrashoutSeverity, Verdict
    from mightymodels_core.similarity.records import Duplicate
    from mightymodels_core.similarity.repository import SimilarityRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class Journaled:
    number: int
    duplicates: tuple[Duplicate, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class FailureLine:
    day: date
    verdict: Verdict
    severity: CrashoutSeverity
    failure: RedactedText


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutStats:
    entries: int
    severities: tuple[tuple[CrashoutSeverity, int], ...]
    verdicts: tuple[tuple[Verdict, int], ...]
    barked_back: int
    first: CrashoutRecord
    last: CrashoutRecord
    failures: tuple[FailureLine, ...]
    corrective_actions: tuple[str, ...]
    older_left_out: bool


def most_common[Name](names: Iterable[Name]) -> tuple[tuple[Name, int], ...]:
    return tuple(Counter(names).most_common())


def failure_lines(crashout: CrashoutRecord) -> list[FailureLine]:
    return [
        FailureLine(
            day=crashout.at.date(),
            verdict=crashout.verdict,
            severity=crashout.severity,
            failure=failure,
        )
        for failure in crashout.failures
    ]


def standing_actions(journal: Sequence[CrashoutRecord]) -> tuple[str, ...]:
    actions = dict.fromkeys(' '.join(crashout.corrective_action.split()) for crashout in journal)
    return tuple(actions)


def stats_of(journal: Sequence[CrashoutRecord], *, older_left_out: bool) -> CrashoutStats:
    return CrashoutStats(
        entries=len(journal),
        severities=most_common(crashout.severity for crashout in journal),
        verdicts=most_common(crashout.verdict for crashout in journal),
        barked_back=sum(crashout.barked_back for crashout in journal),
        first=journal[0],
        last=journal[-1],
        failures=tuple(line for crashout in journal for line in failure_lines(crashout)),
        corrective_actions=standing_actions(journal),
        older_left_out=older_left_out,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutService:
    crashouts: CrashoutRepository
    similarity: SimilarityRepository
    clock: Clock
    options: CrashoutOptions = field(default_factory=CrashoutOptions)

    def add(self, entry: CrashoutEntry) -> Journaled:
        policy = CrashoutPolicy(entry=entry, options=self.options)
        if problem := policy.get_entry_problem():
            raise problem

        crashout = policy.crashout_record(self.clock.now())
        number = self.crashouts.journal(crashout)
        written = Written(kind='crashout', reference=f'#{number}', text=crashout.root_cause)
        return Journaled(number=number, duplicates=tuple(self.similarity.record_all([written])))

    def stats(self) -> CrashoutStats | None:
        latest = self.crashouts.latest_crashouts()
        if not latest.rows:
            return None

        return stats_of(latest.rows, older_left_out=latest.older_left_out)

    def last(self) -> CrashoutRecord | None:
        return self.crashouts.latest_crashout()
