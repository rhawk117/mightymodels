"""The ticket records the repository hands out: frozen values, never a database row.

A title and a summary are redacted text, which only `redact` produces, so a secret cannot reach
a ticket by the type alone.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText, Slug
    from mightymodels_core.schemas.tickets import TicketScope, TicketStatus


@dataclass(slots=True, kw_only=True, frozen=True)
class Tracker:
    issue: int | None
    jira: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketSection:
    ticket: RedactedText
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
    slug: Slug
    status: TicketStatus
    section: TicketSection
    investigations: tuple[str, ...]
