"""Arguments and results of the `ticket` tool.

A `LinkedInvestigation` is the id of an investigation as a caller names it. It is held to a slug's
length here, and `validate` refuses one that is not a slug.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from mightymodels_plugin.routing import Scope
from mightymodels_plugin.slug import SLUG_LIMIT, Slug
from mightymodels_plugin.tools.request import NameText, ProseText, RequestModel

type LinkedInvestigation = Annotated[str, StringConstraints(max_length=SLUG_LIMIT)]


class TicketAction(StrEnum):
    WRITE = 'write'
    VALIDATE = 'validate'
    SHOW = 'show'
    UPDATE_CONTEXT = 'update-context'


class TicketStatus(StrEnum):
    STAGED = 'staged'
    IN_PROGRESS = 'in-progress'
    CLOSED = 'closed'


class TicketAnswers(RequestModel):
    summary: ProseText
    scope: Scope
    compaction: bool
    branch: NameText
    context: tuple[ProseText, ...]
    issue: int | None = None
    jira: NameText | None = None
    reference_urls: tuple[ProseText, ...] = ()
    investigations: tuple[LinkedInvestigation, ...] = ()


class TicketContext(RequestModel):
    context: tuple[ProseText, ...]


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
