"""What the ticket tools return: the rendered text and, once a ticket is staged, its record."""

from datetime import datetime
from typing import TYPE_CHECKING

from mightymodels_core.vocabulary.tickets import TicketScope, TicketStatus
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from mightymodels_core.tickets import TicketRecord


class TrackerView(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    issue: int | None
    jira: str | None


class TicketSectionView(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    ticket: str
    summary: str
    branch: str
    scope: TicketScope
    plan_first: bool
    auto_escalate: bool
    models: dict[str, str | None]
    tracker: TrackerView
    context: tuple[str, ...]
    validated_at: datetime


class StagedTicketView(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    slug: str
    status: TicketStatus
    section: TicketSectionView
    investigations: tuple[str, ...]

    @property
    def text(self) -> str:
        count = len(self.investigations)
        return f'staged {self.slug} (status {self.status}, {count} investigations)\n'


class TicketView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    staged: StagedTicketView | None = None


def render_written(path: str) -> TicketView:
    return TicketView(text=f'wrote {path}; review it, then run validate\n')


def render_staged(record: TicketRecord, lead: str = '') -> TicketView:
    staged = StagedTicketView.model_validate(record)
    return TicketView(text=f'{lead}{staged.text}', staged=staged)
