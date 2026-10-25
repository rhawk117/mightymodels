"""The ticket tools' requests, and the answers ticket_write turns into core's `TicketAnswers`.

Each text field is held to the length of the column it lands in: a name 255 characters, prose
4000, and an investigation slug a slug's length; `validate` refuses one that is not a slug.

`WriteChoices` is what ticket_write knows once its round is answered: the scope, the compaction
and the branch, each from the request or the form. A branch the request names is taken as a new
branch of that name, so core's `branch_of` decides every branch the same way.
"""

from typing import Annotated, Any

from mightymodels_core.primitives.value_types import SLUG_LIMIT
from mightymodels_core.ticket_closing.records import ClosingLines
from mightymodels_core.tickets import BranchChoice, TicketAnswers
from mightymodels_core.vocabulary.tickets import TicketScope
from pydantic import BaseModel, ConfigDict, StringConstraints

from mightymodels_mcp.server.requests import NameText, ProseText, RequestModel, SlugField

type LinkedInvestigation = Annotated[str, StringConstraints(max_length=SLUG_LIMIT)]


class TicketRequest(RequestModel):
    slug: SlugField


class TicketWriteRequest(RequestModel):
    slug: SlugField
    summary: ProseText
    context: tuple[ProseText, ...]
    scope: TicketScope | None = None
    compaction: bool | None = None
    branch: NameText | None = None
    issue: int | None = None
    jira: NameText | None = None
    reference_urls: tuple[ProseText, ...] = ()
    investigations: tuple[LinkedInvestigation, ...] = ()


class TicketContextRequest(RequestModel):
    slug: SlugField
    context: tuple[ProseText, ...]


class CloseTicketRequest(RequestModel):
    slug: SlugField
    shipped: ProseText = ''
    pr: ProseText | None = None
    gotchas: tuple[ProseText, ...] = ()


class WriteChoices(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    scope: TicketScope
    compaction: bool
    branch: BranchChoice
    branch_name: NameText | None = None


def create_write_choices(request: TicketWriteRequest, form: dict[str, Any]) -> WriteChoices:
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
