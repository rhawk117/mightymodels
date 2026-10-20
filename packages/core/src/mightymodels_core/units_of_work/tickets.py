"""The ticket unit of work: one unit per tool call, the stores and services on it, ticket.yml.

`TicketWork.read` and `TicketWork.write` each open one Unit, and every service call inside shares
it. The services take and return ticket.yml text, so this module reads the file for them and
writes what they return: a write unit stores it through the draft file and a replace before the
unit commits, and an error anywhere in the unit rolls the database back.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.contract import SqliteContractRepository
from mightymodels_core.investigations import SqliteInvestigationRepository
from mightymodels_core.reviews import SqliteReviewDecisionRepository, SqliteReviewRepository
from mightymodels_core.tasks import SqliteAttemptRepository, SqliteTaskRepository
from mightymodels_core.ticket_closing import ClosingService, SqliteClosingRepository
from mightymodels_core.tickets import (
    SqliteTicketRepository,
    TicketService,
    TicketSlot,
    TicketSource,
)

from .entry import read_entry, write_entry
from .errors import MissingTicketError

if TYPE_CHECKING:
    from collections.abc import Generator

    from mightymodels_core.database import Database
    from mightymodels_core.primitives import Clock, RepositoryKey, Slug
    from mightymodels_core.workspace import Workspace

    from .entry import Entry


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketFiles:
    workspace: Workspace

    def slot(self, slug: Slug) -> TicketSlot:
        file = self.workspace.ticket_file(slug)
        return TicketSlot(path=self.workspace.relative_to_root(file), exists=file.is_file())

    def source(self, slug: Slug) -> TicketSource:
        file = self.workspace.ticket_file(slug)
        path = self.workspace.relative_to_root(file)
        try:
            return TicketSource(path=path, text=file.read_text(encoding='utf-8'))
        except FileNotFoundError:
            raise MissingTicketError(path=path) from None


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketReadUnit:
    tickets: TicketService
    closing: ClosingService
    files: TicketFiles


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketWriteUnit:
    tickets: TicketService
    closing: ClosingService
    files: TicketFiles

    def store(self, slug: Slug, text: str) -> None:
        workspace = self.files.workspace
        draft = workspace.ticket_draft(slug)
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(text, encoding='utf-8')
        draft.replace(workspace.ticket_file(slug))


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketWork:
    database: Database
    repository_key: RepositoryKey
    workspace: Workspace
    clock: Clock

    @contextmanager
    def read(self) -> Generator[TicketReadUnit]:
        with read_entry(self.database, self.repository_key) as entry:
            tickets, closing = self.create_services(entry)
            yield TicketReadUnit(
                tickets=tickets, closing=closing, files=TicketFiles(workspace=self.workspace)
            )

    @contextmanager
    def write(self) -> Generator[TicketWriteUnit]:
        with write_entry(self.database, self.repository_key) as entry:
            tickets, closing = self.create_services(entry)
            yield TicketWriteUnit(
                tickets=tickets, closing=closing, files=TicketFiles(workspace=self.workspace)
            )

    def create_services(self, entry: Entry) -> tuple[TicketService, ClosingService]:
        unit = entry.unit
        repository_id = entry.repository_id
        ticket_store = SqliteTicketRepository(unit=unit, repository_id=repository_id)
        investigations = SqliteInvestigationRepository(unit=unit, repository_id=repository_id)
        tickets = TicketService(
            tickets=ticket_store, investigations=investigations, clock=self.clock
        )
        closing = ClosingService(
            tickets=ticket_store,
            tasks=SqliteTaskRepository(unit=unit),
            attempts=SqliteAttemptRepository(unit=unit),
            contracts=SqliteContractRepository(unit=unit),
            reviews=SqliteReviewRepository(unit=unit, repository_id=repository_id),
            decisions=SqliteReviewDecisionRepository(unit=unit, repository_id=repository_id),
            investigations=investigations,
            closings=SqliteClosingRepository(unit=unit),
            clock=self.clock,
        )
        return tickets, closing
