"""The `main-thread-hook` subcommand, which the plugin's PreToolUse hook on `Edit`, `Write` and
`Bash` runs.

While the checked-out branch has one unclosed ticket the main thread hands repository edits to a
worker and pushes only a proven landing. The caller rule is the dispatch hook's: a caller whose
`agent_type` begins `mightymodels:` is a plugin worker and gets no decision here, and every other
caller is judged as the main thread. Input that is not a JSON object never reaches this module;
the command exits 2 on it, and hooks/main-thread-hook.sh turns that into a block for a push.

An `Edit` or `Write` whose `file_path` is in a ticket directory gets no decision and reads no
state. Any other one is answered `ask` while the branch has one unclosed ticket, so the user
approves it in the permission prompt. When the tickets cannot be read the edit goes ahead and the
user is shown one line saying it was not checked.

A `Bash` command that names no push gets no decision and reads no state. One that does is denied,
with what is still open and the step to take, until the ticket is ready to land, and when that
cannot be read.

With no unclosed ticket on the branch neither tool gets a decision. With several neither does, and
the user is shown one line naming them.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mightymodels_core.primitives import encode_compact

from mightymodels_hooks.branch_state import BranchState
from mightymodels_hooks.hook_context import create_hook_context_at
from mightymodels_hooks.payloads import plugin_caller_of
from mightymodels_hooks.push_command import names_a_push
from mightymodels_hooks.rulings import Asked, Denied, Unjudged, hook_output

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_hooks.branch_state import BranchTicketsOrUnreadable, LandingOrUnreadable
    from mightymodels_hooks.payloads import PreToolUsePayload
    from mightymodels_hooks.rulings import Ruling

EDIT_TOOLS = frozenset({'Edit', 'Write'})
BASH_TOOL = 'Bash'
EDIT_OUTSIDE = (
    'mightymodels: ticket {slug} is unclosed on the checked-out branch, and this {tool} of {path} '
    'is outside the ticket directories under `.mightymodels/`. The main thread hands a repository '
    'edit to a worker through a started task; approve this one only if the main thread should '
    'make it.'
)
EDIT_UNREADABLE = (
    'mightymodels did not check the {tool} of {path} against an unclosed ticket: the tickets on '
    'the checked-out branch could not be read ({error})'
)
EDIT_SEVERAL_TICKETS = (
    'mightymodels did not check the {tool} of {path} against an unclosed ticket: the checked-out '
    'branch has {count} unclosed tickets ({names}), and the hook acts only when it has one'
)
PUSH_HELD = (
    '`git push` was refused: ticket {slug}, whose branch is checked out, is not ready to land: '
    '{unproven}. Close the tasks still open, then land through the `stick-the-landing` skill, '
    'whose step 1 proves the contract at HEAD with `mightymodels verify run --slug {slug} --all '
    '--phase landing`; the push goes through once that has passed. The hook also holds a command '
    'whose words `git` and `push` it cannot place, so reword one that is no push.'
)
PUSH_UNREADABLE = (
    '`git push` was refused: the tasks and receipts of the ticket on the checked-out branch could '
    'not be read ({error}), so a proven landing cannot be told from none. Push again once the '
    'state can be read.'
)
PUSH_SEVERAL_TICKETS = (
    'mightymodels did not hold this `git push`: the checked-out branch has {count} unclosed '
    'tickets ({names}), and the hook acts only when it has one'
)


@runtime_checkable
class TicketOnBranch(Protocol):
    def ticket_directory_holds(self, file_path: str) -> bool: ...

    async def tickets_on_branch(self) -> BranchTicketsOrUnreadable: ...

    async def landing_on_branch(self) -> LandingOrUnreadable: ...


def outside_edit_ruling(tool: str, file_path: str, tickets: BranchTicketsOrUnreadable) -> Ruling:
    if isinstance(tickets, Exception):
        return Unjudged(warning=EDIT_UNREADABLE.format(tool=tool, path=file_path, error=tickets))

    if len(tickets.unclosed) > 1:
        warning = EDIT_SEVERAL_TICKETS.format(
            tool=tool,
            path=file_path,
            count=len(tickets.unclosed),
            names=', '.join(tickets.unclosed),
        )
        return Unjudged(warning=warning)

    if len(tickets.unclosed) == 0:
        return None

    return Asked(reason=EDIT_OUTSIDE.format(slug=tickets.unclosed[0], tool=tool, path=file_path))


async def edit_ruling(tool: str, file_path: str, ticket: TicketOnBranch) -> Ruling:
    if ticket.ticket_directory_holds(file_path):
        return None

    return outside_edit_ruling(tool, file_path, await ticket.tickets_on_branch())


def push_ruling(landing: LandingOrUnreadable) -> Ruling:
    if isinstance(landing, Exception):
        return Denied(reason=PUSH_UNREADABLE.format(error=landing))

    if len(landing.unclosed) > 1:
        names = ', '.join(landing.unclosed)
        return Unjudged(
            warning=PUSH_SEVERAL_TICKETS.format(count=len(landing.unclosed), names=names)
        )

    if len(landing.unclosed) == 0 or len(landing.unproven) == 0:
        return None

    unproven = '; '.join(landing.unproven)
    return Denied(reason=PUSH_HELD.format(slug=landing.unclosed[0], unproven=unproven))


async def tool_ruling(payload: PreToolUsePayload, ticket: TicketOnBranch) -> Ruling:
    tool = payload.tool_name
    tool_input = payload.tool_input
    if tool is None or tool_input is None:
        return None

    file_path = tool_input.get('file_path')
    command = tool_input.get('command')
    if tool in EDIT_TOOLS and isinstance(file_path, str):
        return await edit_ruling(tool, file_path, ticket)

    if tool == BASH_TOOL and isinstance(command, str) and names_a_push(command):
        return push_ruling(await ticket.landing_on_branch())

    return None


async def main_thread_ruling(payload: PreToolUsePayload, ticket: TicketOnBranch) -> Ruling:
    if plugin_caller_of(payload.agent_type) is not None:
        return None

    return await tool_ruling(payload, ticket)


@dataclass(slots=True, kw_only=True, frozen=True)
class MainThreadHandler:
    environ: Mapping[str, str]

    async def handle(self, payload: PreToolUsePayload) -> str | None:
        state = BranchState(context=create_hook_context_at(self.environ, payload.cwd))
        ruling = await main_thread_ruling(payload, state)
        return None if ruling is None else encode_compact(hook_output(ruling)).decode()
