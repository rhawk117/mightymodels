"""The ticket tools' requests, and the answers ticket_write turns into core's `TicketAnswers`.

Each text field is held to the length of the column it lands in: a name 255 characters, prose
4000, and an investigation slug a slug's length; `validate` refuses one that is not a slug.

`WriteChoices` is what ticket_write knows once its round is answered: the scope, the compaction
and the branch, each from the request or the form. A branch the request names is taken as a new
branch of that name, so core's `branch_of` decides every branch the same way.
"""

from typing import Annotated, Any

from mightymodels_core.primitives import StateError
from mightymodels_core.primitives.value_types import SLUG_LIMIT
from mightymodels_core.ticket_closing.records import ClosingLines
from mightymodels_core.tickets import BranchChoice, TicketAnswers
from mightymodels_core.vocabulary.tickets import TicketScope
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from mightymodels_mcp.server.requests import (
    NAME_LIMIT,
    NameText,
    ProseText,
    RequestModel,
    RevisionField,
    SlugField,
)

type LinkedInvestigation = Annotated[str, StringConstraints(max_length=SLUG_LIMIT)]


BRANCH_NAME_FIELD = 'branch_name'


class BranchNameTooLongError(StateError):
    def __init__(self, *, limit: int) -> None:
        self.limit = limit
        super().__init__(f'{BRANCH_NAME_FIELD} is longer than {limit} characters')


class TicketRequest(RequestModel):
    slug: SlugField


class TicketWriteRequest(RequestModel):
    slug: SlugField
    summary: ProseText = Field(description='What the ticket is for, in a few sentences.')
    context: tuple[ProseText, ...] = Field(
        description='The facts a worker needs about the ticket, one entry per fact.'
    )
    scope: TicketScope | None = Field(
        default=None,
        description='How big the ticket is; omit it and the user is asked.',
    )
    compaction: bool | None = Field(
        default=None,
        description='Whether to plan first and compact; omit it and the user is asked.',
    )
    branch: RevisionField | None = Field(
        default=None,
        description='The name of a new git branch for the ticket; omit it and the user is asked.',
    )
    issue: int | None = Field(
        default=None, description='The GitHub issue number the ticket tracks.'
    )
    jira: NameText | None = Field(default=None, description='The Jira key the ticket tracks.')
    reference_urls: tuple[ProseText, ...] = Field(
        default=(), description='URLs worth keeping with the ticket, such as docs or related work.'
    )
    investigations: tuple[LinkedInvestigation, ...] = Field(
        default=(), description='Slugs of the investigations this ticket draws on.'
    )


class TicketContextRequest(RequestModel):
    slug: SlugField
    context: tuple[ProseText, ...] = Field(
        description='The new context entries that replace the ticket context, one per fact.'
    )


class CloseTicketRequest(RequestModel):
    slug: SlugField
    shipped: ProseText = Field(
        default='', description='One line on what the ticket delivered; closing needs it.'
    )
    pr: ProseText | None = Field(
        default=None, description='The pull request URL or number, if the work has one.'
    )
    gotchas: tuple[ProseText, ...] = Field(
        default=(),
        description='Surprises a later reader of the archive should know, one per entry.',
    )


class WriteChoices(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    scope: TicketScope
    compaction: bool
    branch: BranchChoice
    branch_name: NameText | None = None


def create_write_choices(request: TicketWriteRequest, form: dict[str, Any]) -> WriteChoices:
    answered = form.get(BRANCH_NAME_FIELD) or ''
    if len(answered) > NAME_LIMIT:
        raise BranchNameTooLongError(limit=NAME_LIMIT)

    given = request.model_dump(include={'scope', 'compaction'}, exclude_none=True)
    named = {} if request.branch is None else {'branch': 'new', 'branch_name': request.branch}
    return WriteChoices.model_validate(given | named | form)


def create_ticket_answers(
    request: TicketWriteRequest, choices: WriteChoices, branch: str
) -> TicketAnswers:
    return TicketAnswers(
        summary=request.summary,
        context=request.context,
        scope=choices.scope,
        plan_first=choices.compaction,
        branch=branch,
        issue=request.issue,
        jira=request.jira,
        reference_urls=request.reference_urls,
        investigations=request.investigations,
    )


def create_closing_lines(request: CloseTicketRequest) -> ClosingLines:
    return ClosingLines(shipped=request.shipped, pr=request.pr, gotchas=request.gotchas)
