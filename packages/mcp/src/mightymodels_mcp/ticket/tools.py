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
from mightymodels_mcp.server.annotations import CLOSES, READS, WRITES
from mightymodels_mcp.server.icons import load_icon
from mightymodels_mcp.server.registration import ToolDefinition, open_tool_state

from .close_facts import CloseAttempt, gather_close_facts
from .schemas import (
    CloseTicketRequest,
    TicketContextRequest,
    TicketRequest,
    TicketWriteRequest,
    create_closing_lines,
    create_ticket_answers,
    create_write_choices,
)
from .use_cases import (
    check_close,
    close_ticket_work,
    create_ticket_work,
    prepare_close,
    show_ticket,
    update_ticket_context,
    validate_ticket,
    write_ticket,
)
from .views import CloseView, TicketView

if TYPE_CHECKING:
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
    field_name='branch_name',
    answers='branch',
    title='New branch name',
    description='The name of the new branch; leave it blank for the current branch.',
)
NAMED_BRANCH = replace(BRANCH, prompt='branch (the current branch name, or the new branch name)')
WRITE_ROUND = ChoiceRound(
    message='Answer what the ticket still needs',
    questions=(SCOPE, COMPACTION, BRANCH),
    texts=(BRANCH_NAME,),
)


RoundAsk = Elicit[BaseModel] | BaseModel


def ask_write_round(request: TicketWriteRequest) -> RoundAsk:
    return WRITE_ROUND.omitted_by(request).ask()


WRITE_ROUND_RESOLVER = Resolve(ask_write_round)


def describe_unanswered(request: TicketWriteRequest) -> str:
    omitted = WRITE_ROUND.omitted_by(request).questions
    passed = (NAMED_BRANCH if question is BRANCH else question for question in omitted)
    return needs_input_text(passed)


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
    async with open_tool_state(ctx) as state:
        branch = await name_branch(choices, state.git)
        ticket_answers = create_ticket_answers(request, choices, branch)
        return write_ticket(create_ticket_work(state), request.slug, ticket_answers)


async def ticket_validate(request: TicketRequest, ctx: ToolContext) -> TicketView:
    """Validate ticket.yml and stage the ticket with the investigations it declares."""
    async with open_tool_state(ctx) as state:
        return validate_ticket(create_ticket_work(state), request.slug)


async def ticket_show(request: TicketRequest, ctx: ToolContext) -> TicketView:
    """Show a staged ticket's record."""
    async with open_tool_state(ctx) as state:
        return show_ticket(create_ticket_work(state), request.slug)


async def ticket_update_context(request: TicketContextRequest, ctx: ToolContext) -> TicketView:
    """Replace the context lines of ticket.yml, then stage the ticket again."""
    async with open_tool_state(ctx) as state:
        return update_ticket_context(create_ticket_work(state), request.slug, request.context)


async def close_check(request: TicketRequest, ctx: ToolContext) -> CloseView:
    """List what still blocks closing a ticket; changes nothing."""
    async with open_tool_state(ctx) as state:
        work = create_ticket_work(state)
        prepared = prepare_close(work, request.slug)
        facts = await gather_close_facts(state.git, prepared)
        return check_close(work, request.slug, facts)


async def close_ticket(request: CloseTicketRequest, ctx: ToolContext) -> CloseView:
    """Close a ticket with no live work left and write its archive."""
    async with open_tool_state(ctx) as state:
        work = create_ticket_work(state)
        prepared = prepare_close(work, request.slug)
        facts = await gather_close_facts(state.git, prepared)
        lines = create_closing_lines(request)
        return close_ticket_work(
            work, CloseAttempt(slug=request.slug, prepared=prepared, facts=facts, lines=lines)
        )


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
    close_icon = load_icon('close')
    check = ToolDefinition(
        name='close_check',
        title='Check a ticket for live work',
        annotations=READS,
        icon=close_icon,
        request_model=TicketRequest,
        result_model=CloseView,
        handler=close_check,
    )
    close = ToolDefinition(
        name='close_ticket',
        title='Close a ticket',
        annotations=CLOSES,
        icon=close_icon,
        request_model=CloseTicketRequest,
        result_model=CloseView,
        handler=close_ticket,
    )
    opened = catalog.register(write).register(validate).register(show).register(update_context)
    return opened.register(check).register(close)
