"""The `dispatch-hook` subcommand, which the plugin's PreToolUse hook on `Agent` runs.

Claude Code lets a subagent dispatch any subagent type and ignores an allow-list in a subagent's
definition, so the plugin enforces the "delegate only to" lines of its agent files here. A call
made inside a subagent carries `agent_type`, and the main conversation's does not. The rows police
only this plugin's workers, whose `agent_type` begins `mightymodels:`: a worker's dispatch outside
its row is denied, and a name under that prefix that is no worker has no row. Input that is not a
JSON object never reaches this module; the command exits 2 on it, and hooks/dispatch-hook.sh turns
that into a block for a worker caller.

Every other caller is judged as the main thread. Its dispatch of the engineer or the architect is
denied, with the step to take, while the one unclosed ticket on the checked-out branch has no task
in progress, and when the tickets cannot be read. With no unclosed ticket on the branch it gets no
decision. With several it gets no decision either, and the user is shown one line naming them.

Its dispatch of the architect or the wingman is an escalation, and the owner hears of a block
before one is spent on it. While the one unclosed ticket on the checked-out branch has a task a
block stopped and the ticket's `auto-escalate` is off, the dispatch is answered `ask`, naming each
such task with the reasons of its block. For the architect the denial above comes first.

Its dispatch of any other worker but the intern gets no decision and reads no state.

One rule holds whoever the caller is. The intern takes only a tiny task, so a dispatch of the
intern that the rows let through is denied unless the intern has a task in progress on the ticket
whose branch is checked out and every such task owns exactly one file.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

from mightymodels_core.primitives import AgentName, encode_compact

from mightymodels_hooks.branch_state import BranchState
from mightymodels_hooks.hook_context import create_hook_context
from mightymodels_hooks.rulings import Asked, Denied, Unjudged, hook_output
from mightymodels_hooks.workers import agent_type, plugin_caller, worker_named

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mightymodels_core.vocabulary.tasks import Worker as TaskWorker

    from mightymodels_hooks.branch_state import (
        BlockedTask,
        BranchTicketsOrUnreadable,
        StartedOrUnreadable,
    )
    from mightymodels_hooks.cli import HookPayload
    from mightymodels_hooks.rulings import Ruling

NO_TARGETS = frozenset[AgentName]()
TINY_OWNED_FILES = 1
NO_STARTED_TASK = 'no task is started for the intern on the ticket whose branch is checked out'
STARTED_UNREADABLE = 'the started task could not be read ({error})'
NO_TASK_IN_PROGRESS = (
    '{target} was refused: ticket {slug}, whose branch is checked out, has no task in progress. '
    'Start the task with the `task` tool (action `start`, `by` naming this worker), then dispatch '
    'again.'
)
TICKETS_UNREADABLE = (
    '{target} was refused: the tasks in progress could not be read ({error}), so a started task '
    'cannot be told from none. Dispatch again once the state can be read.'
)
SEVERAL_TICKETS = (
    'mightymodels did not check the dispatch of {target} for a started task: the checked-out '
    'branch has {count} unclosed tickets ({names}), and the hook acts only when it has one'
)
STARTED_BEFORE_DISPATCH = frozenset({'engineer', 'architect'})
ESCALATIONS = frozenset({'architect', 'wingman'})
BLOCK_GOES_TO_THE_OWNER_FIRST = (
    '{target} was held for the owner: ticket {slug}, whose branch is checked out, has a task a '
    'block stopped ({blocks}), and its `auto-escalate` is off. Approve this dispatch to '
    'escalate, or decline it and say what to do about the block. `auto-escalate: true` under '
    '`handoff-context` in ticket.yml, validated with the `ticket` tool, lets an escalation '
    'through without this question.'
)


@runtime_checkable
class StartedTasks(Protocol):
    async def started_by(self, worker: TaskWorker) -> StartedOrUnreadable: ...

    async def tickets_on_branch(self) -> BranchTicketsOrUnreadable: ...


def target_of(fields: Mapping[str, object]) -> object:
    tool_input = fields.get('tool_input')
    return tool_input.get('subagent_type') if isinstance(tool_input, dict) else None


def allowed_names(allowed: frozenset[AgentName]) -> str:
    return ', '.join(sorted(allowed)) or 'nothing'


type DispatchRows = dict[AgentName, frozenset[AgentName]]


@dataclass(slots=True, kw_only=True, frozen=True)
class DispatchRules:
    rows: DispatchRows = field(default_factory=dict)

    def mount(self, rows: DispatchRows) -> Self:
        self.rows.update(rows)
        return self

    def allowed_for(self, caller: str) -> frozenset[AgentName]:
        worker = worker_named(caller)
        return NO_TARGETS if worker is None else self.rows[worker]


def create_dispatch_rules() -> DispatchRules:
    return DispatchRules().mount({
        'code-scout': NO_TARGETS,
        'web-scout': NO_TARGETS,
        'qualitylens': NO_TARGETS,
        'fact-checker': NO_TARGETS,
        'engineer': frozenset({'code-scout'}),
        'architect': frozenset({'code-scout'}),
        'intern': NO_TARGETS,
        'gitty-up': NO_TARGETS,
        'wingman': NO_TARGETS,
        'terry-toolchain': NO_TARGETS,
        'merge-vader': frozenset({'code-scout', 'web-scout', 'qualitylens'}),
        'uncle-bob': frozenset({'code-scout', 'qualitylens'}),
    })


def denial_for_worker(caller: str, target: object, rules: DispatchRules) -> str | None:
    if not isinstance(target, str):
        return f'{caller} was refused a dispatch: the hook input names no target type'

    allowed = rules.allowed_for(caller)
    worker = worker_named(target)
    if worker is not None and worker in allowed:
        return None

    return f'{caller} may not dispatch {target}; it may dispatch: {allowed_names(allowed)}'


def intern_refusal(why: str) -> str:
    return (
        f'{agent_type("intern")} was refused: {why}. The intern takes only a tiny task, '
        f'one that owns exactly one file; dispatch {agent_type("engineer")} instead.'
    )


def intern_denial(started: StartedOrUnreadable) -> str | None:
    if isinstance(started, Exception):
        return intern_refusal(STARTED_UNREADABLE.format(error=started))

    if len(started) == 0:
        return intern_refusal(NO_STARTED_TASK)

    not_tiny = [
        f'{task.id} owns {len(task.owned)} files'
        for task in started
        if len(task.owned) != TINY_OWNED_FILES
    ]
    return intern_refusal('; '.join(not_tiny)) if not_tiny else None


def unstarted_ruling(target: str, tickets: BranchTicketsOrUnreadable) -> Ruling:
    if isinstance(tickets, Exception):
        return Denied(reason=TICKETS_UNREADABLE.format(target=target, error=tickets))

    if len(tickets.unclosed) > 1:
        names = ', '.join(tickets.unclosed)
        warning = SEVERAL_TICKETS.format(target=target, count=len(tickets.unclosed), names=names)
        return Unjudged(warning=warning)

    if len(tickets.unclosed) == 0 or tickets.in_progress:
        return None

    return Denied(reason=NO_TASK_IN_PROGRESS.format(target=target, slug=tickets.unclosed[0]))


def block_line(task: BlockedTask) -> str:
    return f'{task.id} {task.status}: {"; ".join(task.reasons)}'


def escalation_ruling(target: str, tickets: BranchTicketsOrUnreadable) -> Ruling:
    if isinstance(tickets, Exception) or tickets.auto_escalate or not tickets.blocked:
        return None

    blocks = ' | '.join(map(block_line, tickets.blocked))
    reason = BLOCK_GOES_TO_THE_OWNER_FIRST.format(
        target=target, slug=tickets.unclosed[0], blocks=blocks
    )
    return Asked(reason=reason)


def ticket_ruling(target: AgentName, tickets: BranchTicketsOrUnreadable) -> Ruling:
    named = agent_type(target)
    if target in STARTED_BEFORE_DISPATCH and (unstarted := unstarted_ruling(named, tickets)):
        return unstarted

    return escalation_ruling(named, tickets) if target in ESCALATIONS else None


async def started_ruling(caller: str | None, target: AgentName, started: StartedTasks) -> Ruling:
    if target == 'intern':
        refused = intern_denial(await started.started_by('intern'))
        return None if refused is None else Denied(reason=refused)

    if caller is None and target in STARTED_BEFORE_DISPATCH | ESCALATIONS:
        return ticket_ruling(target, await started.tickets_on_branch())

    return None


async def dispatch_ruling(
    fields: Mapping[str, object], started: StartedTasks, rules: DispatchRules
) -> Ruling:
    caller = plugin_caller(fields)
    target = target_of(fields)
    if caller is not None and (refused := denial_for_worker(caller, target, rules)) is not None:
        return Denied(reason=refused)

    worker = worker_named(target) if isinstance(target, str) else None
    return None if worker is None else await started_ruling(caller, worker, started)


@dataclass(slots=True, kw_only=True, frozen=True)
class DispatchHandler:
    environ: Mapping[str, str]
    rules: DispatchRules

    async def handle(self, payload: HookPayload) -> str | None:
        state = BranchState(context=create_hook_context(self.environ, payload))
        ruling = await dispatch_ruling(payload, state, self.rules)
        return None if ruling is None else encode_compact(hook_output(ruling)).decode()
