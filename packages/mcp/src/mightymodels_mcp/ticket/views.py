"""What the ticket tools return: the rendered text and, once a ticket is staged, its record."""

from datetime import datetime
from typing import TYPE_CHECKING

from mightymodels_core.vocabulary.tickets import TicketScope, TicketStatus
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import Slug
    from mightymodels_core.ticket_closing.services import CloseCheck
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


class ArchivePathsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    markdown_path: str
    record_path: str


class CloseView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    blocked: bool
    blockers: tuple[str, ...] = ()
    archive: ArchivePathsView | None = None


def render_git_note(refusal: str | None) -> str:
    return '' if refusal is None else f'git was not consulted: {refusal}\n'


def render_blocked(heading: str, blockers: Sequence[str], refusal: str | None) -> CloseView:
    listed = ''.join(f'  - {blocker}\n' for blocker in blockers)
    text = f'{heading}\n{listed}{render_git_note(refusal)}'
    return CloseView(text=text, blocked=True, blockers=tuple(blockers))


def render_close_check(slug: Slug, check: CloseCheck) -> CloseView:
    if check.blocked:
        return render_blocked('live work remains', check.blockers, check.git_refusal)

    text = f'{slug} has no live work\n{render_git_note(check.git_refusal)}'
    return CloseView(text=text, blocked=False)


def render_closed(slug: Slug, archive: ArchivePathsView, refusal: str | None) -> CloseView:
    text = f'closed {slug}; archive at {archive.markdown_path}\n{render_git_note(refusal)}'
    return CloseView(text=text, blocked=False, archive=archive)
