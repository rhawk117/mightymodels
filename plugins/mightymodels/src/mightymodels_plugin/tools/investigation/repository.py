"""An investigation's ledger entries, reached only through a repository.

`investigation_transaction` opens a transaction on the database and hands out the repository,
which holds that transaction's session, so the investigation service never sees a session. A
domain that reads a ledger inside its own transaction builds an `InvestigationRepository` on that
transaction's session. The repository holds the key of the git repository the database was opened
for, and reads and writes entries under that key only.

An investigation has no row of its own. It exists once its target is stored, which is entry 1 of
its ledger, so `has_entries` asks for that row. `append` is the only write and nothing updates or
deletes an entry: a later entry retires an earlier one by naming it in `supersedes`.

`LedgerRecord` is one entry as it is stored.
"""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.repository_key import RepositoryKey
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.investigation.schema import EntryKind, Source
from mightymodels_plugin.tools.investigation.tables import LedgerEntryRow

TARGET_SEQ = 1


@dataclass(slots=True, kw_only=True, frozen=True)
class LedgerRecord:
    seq: int
    round: int
    kind: EntryKind
    text: str
    source: Source
    cite: str | None
    supersedes: tuple[int, ...]
    at: str
    head: str | None


def entry_row(
    investigation: Slug, record: LedgerRecord, *, repository_key: RepositoryKey
) -> LedgerEntryRow:
    return LedgerEntryRow(
        repository_key=repository_key.root,
        investigation_id=investigation.root,
        seq=record.seq,
        round=record.round,
        kind=record.kind,
        text=record.text,
        source=record.source,
        cite=record.cite,
        supersedes=list(record.supersedes),
        at=record.at,
        head=record.head,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationRepository:
    session: Session
    repository_key: RepositoryKey

    def has_entries(self, investigation: Slug) -> bool:
        target = (self.repository_key.root, investigation.root, TARGET_SEQ)
        return self.session.get(LedgerEntryRow, target) is not None

    def entry_rows(self, investigation: Slug) -> list[LedgerEntryRow]:
        query = (
            select(LedgerEntryRow)
            .where(
                LedgerEntryRow.repository_key == self.repository_key.root,
                LedgerEntryRow.investigation_id == investigation.root,
            )
            .order_by(LedgerEntryRow.seq)
        )
        return list(self.session.scalars(query))

    def latest_rounds(self) -> dict[str, int]:
        query = (
            select(LedgerEntryRow.investigation_id, func.max(LedgerEntryRow.round))
            .where(LedgerEntryRow.repository_key == self.repository_key.root)
            .group_by(LedgerEntryRow.investigation_id)
            .order_by(LedgerEntryRow.investigation_id)
        )
        return dict(self.session.execute(query).all())

    def append(self, investigation: Slug, records: Iterable[LedgerRecord]) -> None:
        self.session.add_all(
            entry_row(investigation, record, repository_key=self.repository_key)
            for record in records
        )


@contextmanager
def investigation_transaction(database: Database) -> Generator[InvestigationRepository]:
    with database.transaction() as session:
        yield InvestigationRepository(session=session, repository_key=database.repository_key)
