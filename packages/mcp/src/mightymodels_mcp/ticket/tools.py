"""The ticket tools: thin async handlers over the sync use cases, and their registration.

ticket_write asks one form for the scope, the compaction and the branch the call leaves out. The
branch is a choice of the current branch or a new one, beside a text field for the new name; the
branch the call names stands in for both. A declined or cancelled form returns the needs-input
text as a normal result. The resolver's annotations are read at runtime, so `RoundAsk` is a
module-level plain assignment and `TicketWriteRequest` a runtime import.
"""

from dataclasses import replace
from typing import TYPE_CHECKING

from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.types import ToolAnnotations
from mightymodels_core.tickets import branch_of
from pydantic import BaseModel

from mightymodels_mcp.forms.choices import (
    Choice,
    ChoiceQuestion,
    ChoiceRound,
    TextQuestion,
    answers_of,
)
from mightymodels_mcp.forms.needs_input import needs_input_text
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolDefinition

from .schemas import (
    TicketContextRequest,
    TicketRequest,
    TicketWriteRequest,
    create_ticket_answers,
    create_write_choices,
)
from .use_cases import (
    create_ticket_work,
    show_ticket,
    update_ticket_context,
    validate_ticket,
    write_ticket,
)
from .views import TicketView

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from mightymodels_core.edge import OpenState
    from mightymodels_core.git import Git

    from mightymodels_mcp.forms.choices import ChoiceOutcome
    from mightymodels_mcp.server.registration import ToolCatalog, ToolContext

    from .schemas import WriteChoices

SCOPE = ChoiceQuestion(
    argument='scope',
    title='What is the scope of each anticipated task?',
    description='The size of each task the ticket is expected to break into.',
    choices=(
        Choice(value='sm', title='Small'),
        Choice(value='med', title='Medium'),
        Choice(value='large', title='Large'),
    ),
)
COMPACTION = ChoiceQuestion(
    argument='compaction',
    title='Would implementing this likely cause at least one compaction?',
    description='A yes plans the work before it starts.',
    choices=(Choice(value='true', title='Yes'), Choice(value='false', title='No')),
)
BRANCH = ChoiceQuestion(
    argument='branch',
    title='Run the work on the current branch, or on a new one? A new one needs a name.',
    description='The branch the ticket is worked on.',
    choices=(
        Choice(value='current', title='The current branch'),
        Choice(value='new', title='A new branch'),
    ),
)
BRANCH_NAME = TextQuestion(
    argument='branch_name',
    answers='branch',
    title='New branch name',
    description='The name of the new branch; leave it blank for the current branch.',
)
NAMED_BRANCH = replace(BRANCH, argument='branch (the current branch name, or the new branch name)')
WRITE_ROUND = ChoiceRound(
    message='Answer what the ticket still needs',
    questions=(SCOPE, COMPACTION, BRANCH),
    texts=(BRANCH_NAME,),
)

WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

RoundAsk = Elicit[BaseModel] | BaseModel


def ask_write_round(request: TicketWriteRequest) -> RoundAsk:
    return WRITE_ROUND.omitted_by(request).ask()


WRITE_ROUND_RESOLVER = Resolve(ask_write_round)


def describe_unanswered(request: TicketWriteRequest) -> str:
    omitted = WRITE_ROUND.omitted_by(request).questions
    passed = (NAMED_BRANCH if question is BRANCH else question for question in omitted)
    return needs_input_text(passed)


def open_state(ctx: ToolContext) -> AbstractAsyncContextManager[OpenState]:
    return ctx.request_context.lifespan_context.state.open()


async def name_branch(choices: WriteChoices, git: Git) -> str:
    current = await git.current_branch() if choices.branch == 'current' else None
    named = branch_of(choices.branch, choices.branch_name or '', current)
    if not isinstance(named, str):
        raise named

    return named


async def ticket_write(
    request: TicketWriteRequest, ctx: ToolContext, *, answers: ChoiceOutcome
) -> TicketView:
    """Write ticket.yml for a new ticket; asks the scope, compaction and branch the call omits."""
    form = answers_of(answers)
    if form is None:
        return TicketView(text=describe_unanswered(request))

    choices = create_write_choices(request, form)
    async with open_state(ctx) as state:
        branch = await name_branch(choices, state.git)
        ticket_answers = create_ticket_answers(request, choices, branch)
        return write_ticket(create_ticket_work(state), request.slug, ticket_answers)


async def ticket_validate(request: TicketRequest, ctx: ToolContext) -> TicketView:
    """Validate ticket.yml and stage the ticket with the investigations it declares."""
    async with open_state(ctx) as state:
        return validate_ticket(create_ticket_work(state), request.slug)


async def ticket_show(request: TicketRequest, ctx: ToolContext) -> TicketView:
    """Show a staged ticket's record."""
    async with open_state(ctx) as state:
        return show_ticket(create_ticket_work(state), request.slug)


async def ticket_update_context(request: TicketContextRequest, ctx: ToolContext) -> TicketView:
    """Replace the context lines of ticket.yml, then stage the ticket again."""
    async with open_state(ctx) as state:
        return update_ticket_context(create_ticket_work(state), request.slug, request.context)


def register_ticket_tools(catalog: ToolCatalog) -> ToolCatalog:
    icon = load_icon('ticket')
    write = ToolDefinition(
        name='ticket_write',
        title='Write a ticket',
        annotations=WRITES,
        icon=icon,
        request_model=TicketWriteRequest,
        result_model=TicketView,
        handler=ticket_write,
        resolvers={'answers': WRITE_ROUND_RESOLVER},
    )
    validate = ToolDefinition(
        name='ticket_validate',
        title='Validate a ticket',
        annotations=WRITES,
        icon=icon,
        request_model=TicketRequest,
        result_model=TicketView,
        handler=ticket_validate,
    )
    show = ToolDefinition(
        name='ticket_show',
        title='Show a ticket',
        annotations=READS,
        icon=icon,
        request_model=TicketRequest,
        result_model=TicketView,
        handler=ticket_show,
    )
    update_context = ToolDefinition(
        name='ticket_update_context',
        title="Update a ticket's context",
        annotations=WRITES,
        icon=icon,
        request_model=TicketContextRequest,
        result_model=TicketView,
        handler=ticket_update_context,
    )
    return catalog.register(write).register(validate).register(show).register(update_context)
