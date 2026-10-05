"""The crashout journal, reached only through a repository.

`crashout_transaction` opens a transaction on the database and hands out the repository, which
holds that transaction's session, so the crashout service never sees a session. `journal` is the
only write: it adds one row and answers its number, and nothing updates or deletes a crashout.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.tools.crashout.schema import JournaledCrashout
from mightymodels_plugin.tools.crashout.tables import CrashoutRow


def crashout_row(crashout: JournaledCrashout) -> CrashoutRow:
    return CrashoutRow(
        at=crashout.at,
        ticket=crashout.ticket,
        branch=crashout.branch,
        severity=crashout.severity,
        verdict=crashout.verdict,
        rant=crashout.rant,
        failures=list(crashout.failures),
        root_cause=crashout.root_cause,
        corrective_action=crashout.corrective_action,
        barked_back=crashout.barked_back,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutRepository:
    session: Session

    def rows(self) -> list[CrashoutRow]:
        return list(self.session.scalars(select(CrashoutRow).order_by(CrashoutRow.id)))

    def latest_row(self) -> CrashoutRow | None:
        return self.session.scalars(select(CrashoutRow).order_by(CrashoutRow.id.desc())).first()

    def journal(self, crashout: JournaledCrashout) -> int:
        row = crashout_row(crashout)
        self.session.add(row)
        self.session.flush()
        return row.id


@contextmanager
def crashout_transaction(database: Database) -> Generator[CrashoutRepository]:
    with database.transaction() as session:
        yield CrashoutRepository(session=session)
