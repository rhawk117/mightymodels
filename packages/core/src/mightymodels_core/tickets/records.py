"""The ticket records the repository hands out: frozen values, never a database row.

A summary is redacted text, which only `redact` produces, so a secret cannot reach
a ticket by the type alone.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText, Slug
    from mightymodels_core.vocabulary.tickets import TicketScope, TicketStatus


@dataclass(slots=True, kw_only=True, frozen=True)
class Tracker:
    issue: int | None
    jira: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketSection:
    ticket: str
    summary: RedactedText
    branch: str
    scope: TicketScope
    plan_first: bool
    auto_escalate: bool
    models: dict[str, str | None]
    tracker: Tracker
    context: tuple[str, ...]
    validated_at: datetime


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketRecord:
    id: int
    slug: Slug
    status: TicketStatus
    section: TicketSection
    investigations: tuple[str, ...]


type BranchChoice = Literal['current', 'new']


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketSlot:
    path: str
    exists: bool


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketAnswers:
    summary: str
    context: tuple[str, ...]
    scope: TicketScope
    plan_first: bool
    branch: str
    issue: int | None = None
    jira: str | None = None
    reference_urls: tuple[str, ...] = ()
    investigations: tuple[str, ...] = ()
