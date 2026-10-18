"""The ticket rows, their investigation links and their closings."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Command, Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class TicketStatus(StrEnum):
    STAGED = 'staged'
    IN_PROGRESS = 'in-progress'
    CLOSED = 'closed'


class TicketScope(StrEnum):
    SM = 'sm'
    MED = 'med'
    LARGE = 'large'


class TicketIdParams(Struct, frozen=True, kw_only=True, gc=False):
    id: int


class TicketSlugParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    slug: str


class StageTicketParams(Struct, frozen=True, kw_only=True):
    repository_id: int
    slug: str
    ticket: str
    summary: str
    branch: str
    scope: TicketScope
    plan_first: bool
    auto_escalate: bool
    issue: int | None
    jira: str | None
    models: dict[str, str | None]
    context: list[str]
    validated_at: datetime


class SetTicketStatusParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    slug: str
    status: TicketStatus


class BranchParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    branch: str


class LinkTicketInvestigationParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int
    investigation_id: int


class UpsertClosingParams(Struct, frozen=True, kw_only=True):
    ticket_id: int
    closed_at: datetime
    head: str | None
    shipped: str
    pr: str | None
    gotchas: list[str]
    archive: str


class ClosingParams(Struct, frozen=True, kw_only=True, gc=False):
    ticket_id: int


class TicketRow(Struct, frozen=True, kw_only=True):
    id: int
    slug: str
    status: TicketStatus
    ticket: str
    summary: str
    branch: str
    scope: TicketScope
    plan_first: bool
    auto_escalate: bool
    issue: int | None
    jira: str | None
    models: dict[str, str | None]
    context: list[str]
    validated_at: datetime
    investigations: list[str]


class TicketIdRow(Struct, frozen=True, kw_only=True, gc=False):
    id: int


class SlugRow(Struct, frozen=True, kw_only=True, gc=False):
    slug: str


class ClosingRow(Struct, frozen=True, kw_only=True):
    ticket_id: int
    closed_at: datetime
    head: str | None
    shipped: str
    pr: str | None
    gotchas: list[str]
    archive: str


TICKET_BY_ID = Query(name='ticket_by_id', params=TicketIdParams, row=TicketRow)
TICKET_BY_SLUG = Query(name='ticket_by_slug', params=TicketSlugParams, row=TicketRow)
STAGE_TICKET = Query(name='stage_ticket', params=StageTicketParams, row=TicketIdRow)
SET_TICKET_STATUS = Command(name='set_ticket_status', params=SetTicketStatusParams)
UNCLOSED_SLUGS_ON_BRANCH = Query(name='unclosed_slugs_on_branch', params=BranchParams, row=SlugRow)
UNCLOSED_SLUG_PAIR_ON_BRANCH = Query(
    name='unclosed_slug_pair_on_branch', params=BranchParams, row=SlugRow
)
LINK_TICKET_INVESTIGATION = Command(
    name='link_ticket_investigation', params=LinkTicketInvestigationParams
)
UPSERT_CLOSING = Command(name='upsert_closing', params=UpsertClosingParams)
CLOSING_OF_TICKET = Query(name='closing_of_ticket', params=ClosingParams, row=ClosingRow)

DECLARATIONS: tuple[Declaration, ...] = (
    TICKET_BY_ID,
    TICKET_BY_SLUG,
    STAGE_TICKET,
    SET_TICKET_STATUS,
    UNCLOSED_SLUGS_ON_BRANCH,
    UNCLOSED_SLUG_PAIR_ON_BRANCH,
    LINK_TICKET_INVESTIGATION,
    UPSERT_CLOSING,
    CLOSING_OF_TICKET,
)
