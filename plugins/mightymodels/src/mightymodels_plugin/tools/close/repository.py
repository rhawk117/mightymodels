"""A ticket's closing, written with the ticket's closed status in one transaction.

`close_transaction` opens the snapshot's transaction and hands out the close repository built on
that transaction's session, so the close service never sees a session. The repository carries the
snapshot repository as `recorded`: a closing is blocked by, and archives, what the ticket, task,
contract, review and investigation domains recorded, and it reads those rows in the transaction it
writes in.

`record_closing` is the only write. It marks the ticket closed and stores the closing's row
together, so no ticket reads closed without its closing.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.tools.close.schema import ArchiveRecord
from mightymodels_plugin.tools.close.tables import ClosingRow
from mightymodels_plugin.tools.snapshot.repository import SnapshotRepository, snapshot_transaction


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseRepository:
    session: Session
    recorded: SnapshotRepository

    def record_closing(self, record: ArchiveRecord, *, archive: str) -> None:
        self.recorded.tickets.mark_closed(record.slug)
        self.session.merge(
            ClosingRow(
                slug=record.slug.root,
                closed_at=record.closed_at,
                head=record.head,
                shipped=record.shipped,
                pr=record.pr,
                gotchas=list(record.gotchas),
                archive=archive,
            )
        )


@contextmanager
def close_transaction(database: Database) -> Generator[CloseRepository]:
    with snapshot_transaction(database) as recorded:
        yield CloseRepository(session=recorded.session, recorded=recorded)
