"""The `completion-gate` subcommand, which the SubagentStop hook on the implementers runs.

When `mightymodels:workers:engineer`, `mightymodels:workers:architect` or
`mightymodels:workers:intern` stops while a task it started is still in progress on the ticket
whose branch is checked out, and the task's brief has no DONE half that names a commit (a
`commit: <hash>` line under `## DONE`), the stop is blocked once: the hook prints
`{"decision": "block", "reason": ...}` and the subagent is sent back to finish. The reason names
each task and what its brief lacks.

A residual (an `R` id) has no brief and is held on the rest of what verifies a task: a commit
follows its base, each contract command of its own passed at HEAD, and the commits since its base
touched only the files it owns. The reason names each residual and which of the three it lacks. A
fix for a failing CI check (a `C` id) is not held.

The gate keeps no marker of its own. Claude Code sets `stop_hook_active` on the stop that follows a
block, and the gate lets that one through, so a subagent that cannot finish is never trapped.

A worker with nothing in progress, any other agent type and a stop with no ticket print nothing and
exit 0. So does a stop with no data directory, no git work tree or an unreadable database; those
say why on standard error.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, TextIO

from mightymodels_core.primitives import encode_compact
from mightymodels_core.tasks.gates import (
    Brief,
    Evidence,
    VerificationGate,
    done_commit,
)

from mightymodels_hooks.completion_state import CompletionState
from mightymodels_hooks.hook_context import STATE_UNREADABLE, create_hook_context_at
from mightymodels_hooks.payloads import plugin_caller_of
from mightymodels_hooks.workers import worker_named

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.primitives import AgentName
    from mightymodels_core.vocabulary.tasks import Worker as TaskWorker

    from mightymodels_hooks.completion_state import PlanTask, ResidualFacts, Unfinished
    from mightymodels_hooks.payloads import SubagentStopPayload

type Implementers = dict[AgentName, TaskWorker]
BRIEF_MISSING = 'its brief {brief} is missing'
NO_DONE_COMMIT = 'its brief {brief} has no DONE half naming a commit'
NOTHING_COMMITTED = 'no commit follows its base'
FINISH_A_PLAN_TASK = (
    'Append the `## DONE` half with a `commit: <hash>` line naming your commit, then report.'
)
FINISH_A_RESIDUAL = (
    'Commit the fix inside the files the residual owns and take each receipt named with '
    '`mightymodels verify run --slug {slug} --id <id>`, then report.'
)


def create_implementers() -> Implementers:
    return {'engineer': 'engineer', 'architect': 'architect', 'intern': 'intern'}


def brief_lack(task: PlanTask) -> str | None:
    if task.text is None:
        return BRIEF_MISSING.format(brief=task.brief)

    if done_commit(task.text) is None:
        return NO_DONE_COMMIT.format(brief=task.brief)

    return None


def brief_lines(plan_tasks: Sequence[PlanTask]) -> list[str]:
    lacks = [(task.id, brief_lack(task)) for task in plan_tasks]
    return [f'{task_id} is in progress and {lack}' for task_id, lack in lacks if lack is not None]


def residual_problems(facts: ResidualFacts) -> list[str]:
    head = facts.git.head
    if head is None:
        return [NOTHING_COMMITTED]

    evidence = Evidence(
        commit=head,
        brief=Brief(text=None),
        assertions={},
        commands=facts.commands,
        receipts=facts.receipts,
    )
    gate = VerificationGate(task=facts.task, evidence=evidence, git=facts.git)
    if problems := gate.commit_problems():
        return problems

    if facts.base_commit == head:
        return [NOTHING_COMMITTED]

    return [*gate.receipt_problems(), *gate.ownership_problems()]


def residual_lines(unfinished: Unfinished) -> list[str]:
    lines: list[str] = []
    for facts in unfinished.residuals:
        problems = residual_problems(facts)
        if problems:
            lines.append(f'{facts.task.key} is in progress and {", ".join(problems)}')

    return lines


def unfinished_reason(unfinished: Unfinished) -> str | None:
    briefs = brief_lines(unfinished.plan_tasks)
    residuals = residual_lines(unfinished)
    if not briefs and not residuals:
        return None

    remedies = [
        *([FINISH_A_PLAN_TASK] if briefs else []),
        *([FINISH_A_RESIDUAL.format(slug=unfinished.slug)] if residuals else []),
    ]
    return (
        f'You are stopping with work unfinished on ticket {unfinished.slug}: '
        f'{"; ".join([*briefs, *residuals])}. {" ".join(remedies)}'
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class CompletionGateHandler:
    environ: Mapping[str, str]
    stderr: TextIO
    implementers: Implementers

    async def handle(self, payload: SubagentStopPayload) -> str | None:
        caller = plugin_caller_of(payload.agent_type)
        worker = None if caller is None else worker_named(caller)
        implementer = None if worker is None else self.implementers.get(worker)
        if implementer is None or payload.stop_hook_active is True:
            return None

        state = CompletionState(context=create_hook_context_at(self.environ, payload.cwd))
        try:
            unfinished = await state.unfinished(implementer)
        except STATE_UNREADABLE as error:
            self.stderr.write(f'mightymodels-hooks: completion-gate: {error}\n')
            return None

        reason = None if unfinished is None else unfinished_reason(unfinished)
        if reason is None:
            return None

        return encode_compact({'decision': 'block', 'reason': reason}).decode() + '\n'
