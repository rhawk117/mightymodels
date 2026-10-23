"""The crashout repository over a core unit, working within one repository id."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.crashouts.records import JOURNAL_WINDOW, CrashoutRecord
from mightymodels_core.primitives import redact
from mightymodels_core.schemas.crashouts import (
    CRASHOUT_COUNT,
    JOURNAL_CRASHOUT,
    LATEST_CRASHOUTS,
    CrashoutCountParams,
    JournalCrashoutParams,
    LatestCrashoutsParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Unit
    from mightymodels_core.primitives import Latest
    from mightymodels_core.schemas.crashouts import CrashoutRow


def record_of(row: CrashoutRow) -> CrashoutRecord:
    return CrashoutRecord(
        at=row.at,
        ticket_key=row.ticket_key,
        branch=None if row.branch is None else redact(row.branch),
        severity=row.severity,
        verdict=row.verdict,
        rant=redact(row.rant),
        failures=tuple(redact(failure) for failure in row.failures),
        root_cause=redact(row.root_cause),
        corrective_action=redact(row.corrective_action),
        barked_back=row.barked_back,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteCrashoutRepository:
    unit: Unit
    repository_id: int

    def latest_crashouts(self) -> Latest[CrashoutRecord]:
        params = LatestCrashoutsParams(
            repository_id=self.repository_id, limit=JOURNAL_WINDOW.fetched
        )
        newest_first = [record_of(row) for row in self.unit.all(LATEST_CRASHOUTS, params)]
        return JOURNAL_WINDOW.latest(newest_first)

    def latest_crashout(self) -> CrashoutRecord | None:
        params = LatestCrashoutsParams(repository_id=self.repository_id, limit=1)
        row = self.unit.one(LATEST_CRASHOUTS, params)
        return None if row is None else record_of(row)

    def journal(self, crashout: CrashoutRecord) -> int:
        params = JournalCrashoutParams(
            repository_id=self.repository_id,
            at=crashout.at,
            ticket_key=crashout.ticket_key,
            branch=crashout.branch,
            severity=crashout.severity,
            verdict=crashout.verdict,
            rant=crashout.rant,
            failures=list(crashout.failures),
            root_cause=crashout.root_cause,
            corrective_action=crashout.corrective_action,
            barked_back=crashout.barked_back,
        )
        self.unit.one(JOURNAL_CRASHOUT, params)
        (counted,) = self.unit.all(
            CRASHOUT_COUNT, CrashoutCountParams(repository_id=self.repository_id)
        )
        return counted.count
