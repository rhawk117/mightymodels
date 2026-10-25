"""Builders and constants the ticket tests share, imported by tests and by the conftest."""

from datetime import UTC, datetime
from importlib.resources import files

from mightymodels_core.investigations import InvestigationRecord
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.tickets import (
    TicketAnswers,
    TicketSection,
    TicketService,
    TicketSlot,
    Tracker,
)

from tests.core.investigations.fakes import (
    FakeInvestigationRepository,
    InvestigationLedger,
)
from tests.core.primitives.clock import create_fake_clock
from tests.core.tickets.fakes import FakeTicketRepository

SQL = files('mightymodels_core.sql')
RECORDED_INVESTIGATIONS = ('first-look', 'second-look')
SERVICE_MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)


def create_section(slug: Slug, branch: str) -> TicketSection:
    return TicketSection(
        ticket=f'.mightymodels/{slug}/ticket.yml',
        summary=redact(f'summary of {slug}'),
        branch=branch,
        scope='med',
        plan_first=False,
        auto_escalate=False,
        models={'engineer': 'sonnet'},
        tracker=Tracker(issue=None, jira=None),
        context=('one', 'two'),
        validated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


def create_fake_investigations() -> FakeInvestigationRepository:
    ledger = InvestigationLedger()
    investigations = FakeInvestigationRepository(ledger=ledger)
    for key in RECORDED_INVESTIGATIONS:
        record = InvestigationRecord(key=Slug(key), target=redact(key), kind='behavior')
        investigations.add_investigation(record)
    return investigations


def create_service() -> TicketService:
    return TicketService(
        tickets=FakeTicketRepository(recorded_investigations=RECORDED_INVESTIGATIONS),
        investigations=create_fake_investigations(),
        clock=create_fake_clock(SERVICE_MOMENT),
    )


def create_free_slot() -> TicketSlot:
    return TicketSlot(path='.mightymodels/add-widget/ticket.yml', exists=False)


def create_answers(
    *,
    summary: str = 'add the widget',
    context: tuple[str, ...] = ('one line', 'two lines'),
    investigations: tuple[str, ...] = ('first-look',),
) -> TicketAnswers:
    return TicketAnswers(
        summary=summary,
        context=context,
        scope='large',
        plan_first=True,
        branch='feat/widget',
        issue=7,
        jira='WID-1',
        reference_urls=('https://example.com/a', 'https://example.com/b'),
        investigations=investigations,
    )
