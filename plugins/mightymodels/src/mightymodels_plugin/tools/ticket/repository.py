"""The ticket rows, reached only through a repository that holds one transaction's session.

`ticket_transaction` opens a transaction on the database and hands out the repository, so the
ticket service never sees a session. A domain that reads ticket rows inside its own transaction
builds a `TicketRepository` on that transaction's session.
"""

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mightymodels_plugin.database import Database
from mightymodels_plugin.errors import StateError
from mightymodels_plugin.slug import Slug
from mightymodels_plugin.tools.ticket.schema import TicketSection, TicketStatus
from mightymodels_plugin.tools.ticket.tables import TicketRow


class NotStagedError(StateError):
    def __init__(self, slug: Slug) -> None:
        super().__init__(f'{slug} is not staged; stage the ticket with open-ticket first')
        self.slug = slug


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketRepository:
    session: Session

    def row(self, slug: Slug) -> TicketRow | None:
        return self.session.get(TicketRow, slug.root)

    def staged_row(self, slug: Slug) -> TicketRow:
        row = self.row(slug)
        if row is None:
            raise NotStagedError(slug)
        return row

    def stage(self, slug: Slug, section: TicketSection, declared: Sequence[str]) -> TicketRow:
        existing = self.row(slug)
        previous = [] if existing is None else existing.investigations
        added = [investigation for investigation in declared if investigation not in previous]
        row = TicketRow(
            slug=slug.root,
            status=TicketStatus.STAGED if existing is None else existing.status,
            ticket=section.ticket,
            summary=section.summary,
            branch=section.branch,
            scope=section.scope,
            plan_first=section.plan_first,
            issue=section.tracker.issue,
            jira=section.tracker.jira,
            models=section.models,
            context=list(section.context),
            investigations=[*previous, *added],
            validated_at=section.validated_at,
        )
        return self.session.merge(row)


@contextmanager
def ticket_transaction(database: Database) -> Generator[TicketRepository]:
    with database.transaction() as session:
        yield TicketRepository(session=session)
