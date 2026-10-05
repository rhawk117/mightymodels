"""The crashout service: an append-only journal of crashouts, stored as rows.

`add` journals one crashout with the time the server received it. The rant keeps its words: its
line endings become newlines, the whitespace ending each line goes, and so do the blank lines
around it. Every free-text field is redacted before it is stored. `stats` reports the journal's
recurring patterns and `last` returns the newest crashout, as fields and as text.

The service reads and writes the database and nothing else: no file, and nothing in git.

Everything above the class reads no service state.
"""

from dataclasses import dataclass

from mightymodels_plugin.clock import now
from mightymodels_plugin.database import Database
from mightymodels_plugin.redaction import redact
from mightymodels_plugin.tools.crashout.rendering import crashout_text, patterns_text
from mightymodels_plugin.tools.crashout.repository import crashout_transaction
from mightymodels_plugin.tools.crashout.schema import (
    CrashoutEntry,
    CrashoutView,
    JournaledCrashout,
    Severity,
    Verdict,
)
from mightymodels_plugin.tools.crashout.tables import CrashoutRow

NOTHING_JOURNALED = 'no crashouts recorded yet.'
SERENITY = f'{NOTHING_JOURNALED} serenity.'


def normalized_rant(rant: str) -> str:
    lines = rant.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    return '\n'.join(line.rstrip() for line in lines).strip('\n')


def journaled(entry: CrashoutEntry, *, at: str) -> JournaledCrashout:
    return JournaledCrashout(
        at=at,
        ticket=None if entry.ticket is None else entry.ticket.root,
        branch=None if entry.branch is None else redact(entry.branch),
        severity=entry.severity,
        verdict=entry.verdict,
        rant=redact(normalized_rant(entry.rant)),
        failures=tuple(map(redact, entry.failures)),
        root_cause=redact(entry.root_cause),
        corrective_action=redact(entry.corrective_action),
        barked_back=entry.barked_back,
    )


def crashout_of(row: CrashoutRow) -> JournaledCrashout:
    return JournaledCrashout(
        at=row.at,
        ticket=row.ticket,
        branch=row.branch,
        severity=Severity(row.severity),
        verdict=Verdict(row.verdict),
        rant=row.rant,
        failures=tuple(row.failures),
        root_cause=row.root_cause,
        corrective_action=row.corrective_action,
        barked_back=row.barked_back,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutService:
    database: Database

    def add(self, entry: CrashoutEntry) -> CrashoutView:
        crashout = journaled(entry, at=now())
        with crashout_transaction(self.database) as repository:
            number = repository.journal(crashout)
        return CrashoutView(text=f'journaled crashout #{number}\n')

    def stats(self) -> CrashoutView:
        with crashout_transaction(self.database) as repository:
            journal = tuple(map(crashout_of, repository.rows()))
        return CrashoutView(text=patterns_text(journal) if journal else f'{SERENITY}\n')

    def last(self) -> CrashoutView:
        with crashout_transaction(self.database) as repository:
            row = repository.latest_row()
            if row is None:
                return CrashoutView(text=f'{NOTHING_JOURNALED}\n')
            crashout = crashout_of(row)
        return CrashoutView(text=crashout_text(crashout), entry=crashout)
