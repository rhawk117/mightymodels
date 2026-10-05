"""Arguments and results of the `ticket` tool."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from mightymodels_plugin.routing import Scope
from mightymodels_plugin.slug import Slug


class TicketAction(StrEnum):
    WRITE = 'write'
    VALIDATE = 'validate'
    SHOW = 'show'
    UPDATE_CONTEXT = 'update-context'


class TicketStatus(StrEnum):
    STAGED = 'staged'
    IN_PROGRESS = 'in-progress'


class TicketAnswers(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    summary: str
    scope: Scope
    compaction: bool
    branch: str
    context: tuple[str, ...]
    issue: int | None = None
    jira: str | None = None
    reference_urls: tuple[str, ...] = ()
    investigations: tuple[str, ...] = ()


class TicketContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    context: tuple[str, ...]


type TicketFields = TicketAnswers | TicketContext


class Tracker(BaseModel):
    model_config = ConfigDict(frozen=True)

    issue: int | None
    jira: str | None


class TicketSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticket: str
    summary: str
    branch: str
    scope: Scope
    plan_first: bool
    models: dict[str, str | None]
    tracker: Tracker
    context: tuple[str, ...]
    validated_at: str


class WorkUnit(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: Slug
    status: TicketStatus
    ticket: TicketSection
    investigations: tuple[str, ...]


class TicketView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    unit: WorkUnit | None = None
