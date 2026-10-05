"""What the ticket, task, contract, review and investigation domains recorded, in one transaction.

A snapshot stores nothing and has no table. `snapshot_transaction` opens one transaction on the
database and hands out the five domains' repositories, all built here on that transaction's
session, so the snapshot service never sees a session and one transaction serves every read.

The repository holds that session because the close domain builds its own repository over it:
closing a ticket reads the same rows and writes in the same transaction.
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.tools.contract.repository import ContractRepository
from mightymodels_plugin.tools.investigation.repository import InvestigationRepository
from mightymodels_plugin.tools.review.repository import DecisionRepository, ReviewRepository
from mightymodels_plugin.tools.task.repository import TaskRepository
from mightymodels_plugin.tools.ticket.repository import TicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotRepository:
    session: Session
    tickets: TicketRepository
    tasks: TaskRepository
    contracts: ContractRepository
    reviews: ReviewRepository
    investigations: InvestigationRepository


@contextmanager
def snapshot_transaction(database: Database) -> Generator[SnapshotRepository]:
    with database.transaction() as session:
        tickets = TicketRepository(session=session)
        contracts = ContractRepository(session=session)
        yield SnapshotRepository(
            session=session,
            tickets=tickets,
            tasks=TaskRepository(session=session, tickets=tickets, contracts=contracts),
            contracts=contracts,
            reviews=ReviewRepository(
                session=session, tickets=tickets, decisions=DecisionRepository(session=session)
            ),
            investigations=InvestigationRepository(session=session),
        )
