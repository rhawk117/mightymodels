"""The crashout repository kept in memory."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.crashouts.records import JOURNAL_WINDOW

if TYPE_CHECKING:
    from mightymodels_core.crashouts.records import CrashoutRecord
    from mightymodels_core.primitives import Latest


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutLedger:
    crashouts: list[CrashoutRecord] = field(default_factory=list)


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeCrashoutRepository:
    ledger: CrashoutLedger = field(default_factory=CrashoutLedger)

    def latest_crashouts(self) -> Latest[CrashoutRecord]:
        newest_first = list(reversed(self.ledger.crashouts[-JOURNAL_WINDOW.fetched :]))
        return JOURNAL_WINDOW.latest(newest_first)

    def latest_crashout(self) -> CrashoutRecord | None:
        return self.ledger.crashouts[-1] if self.ledger.crashouts else None

    def journal(self, crashout: CrashoutRecord) -> int:
        self.ledger.crashouts.append(crashout)
        return len(self.ledger.crashouts)
