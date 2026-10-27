"""Fakes, payloads and the seeded state the dispatch tests share."""

import json
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, open_state
from mightymodels_core.primitives import Slug, TaskId
from mightymodels_core.tasks import Attempt, SqliteTaskRepository
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import write_entry
from mightymodels_hooks.branch_state import BranchTickets
from mightymodels_hooks.dispatch import DispatchHandler, dispatch_ruling
from mightymodels_hooks.rulings import hook_output

from tests.core.tasks.repository_builders import create_ticket_section, create_transition

if TYPE_CHECKING:
    from pathlib import Path

    from mightymodels_core.vocabulary.tasks import TaskStatus, Worker
    from mightymodels_hooks.branch_state import (
        BlockedTask,
        BranchTicketsOrUnreadable,
        StartedOrUnreadable,
    )
    from mightymodels_hooks.cli import HookPayload
    from mightymodels_hooks.rulings import Ruling

SLUG = Slug('port-it')
BRANCH = 'feat/port-it'
CLAIM = 'Task T1 is started for you and the ticket allows this dispatch.'


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeStartedTasks:
    started: StartedOrUnreadable = ()
    tickets: BranchTicketsOrUnreadable = field(default_factory=BranchTickets)
    reads: list[str] = field(default_factory=list)

    async def started_by(self, worker: Worker) -> StartedOrUnreadable:
        self.reads.append(worker)
        return self.started

    async def tickets_on_branch(self) -> BranchTicketsOrUnreadable:
        self.reads.append('tickets')
        return self.tickets


@dataclass(slots=True, kw_only=True, frozen=True)
class Verdict:
    decision: str | None
    detail: str


@dataclass(slots=True, kw_only=True, frozen=True)
class SeededTask:
    key: str
    worker: Worker = 'engineer'
    owned: tuple[str, ...] = ('src/a.py',)
    status: TaskStatus = 'in-progress'
    before: TaskStatus = 'pending'
    reasons: tuple[str, ...] = ()


def dispatch_payload(target: object, caller: str | None = None) -> HookPayload:
    tool_input = {'subagent_type': target, 'prompt': CLAIM}
    payload: HookPayload = {'tool_name': 'Agent', 'tool_input': tool_input}
    return payload if caller is None else {**payload, 'agent_type': caller}


def verdict_of(output: str | None) -> Verdict:
    if output is None:
        return Verdict(decision=None, detail='')

    decoded = json.loads(output)
    if 'systemMessage' in decoded:
        return Verdict(decision='message', detail=decoded['systemMessage'])

    specific = decoded['hookSpecificOutput']
    return Verdict(
        decision=specific['permissionDecision'], detail=specific['permissionDecisionReason']
    )


async def judge(
    target: object, fake: FakeStartedTasks | None = None, caller: str | None = None
) -> Verdict:
    payload = dispatch_payload(target, caller)
    ruling: Ruling = await dispatch_ruling(payload, fake or FakeStartedTasks())
    return verdict_of(None if ruling is None else json.dumps(hook_output(ruling)))


def one_ticket(
    *,
    in_progress: tuple[str, ...] = (),
    auto_escalate: bool = False,
    blocked: tuple[BlockedTask, ...] = (),
) -> BranchTickets:
    return BranchTickets(
        unclosed=(SLUG,), in_progress=in_progress, auto_escalate=auto_escalate, blocked=blocked
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class DispatchHarness:
    checkout: Path
    data_directory: Path

    def handler(self) -> DispatchHandler:
        return DispatchHandler(environ={PLUGIN_DATA_VARIABLE: str(self.data_directory)})

    async def verdict(self, target: object, caller: str | None = None) -> Verdict:
        payload = {**dispatch_payload(target, caller), 'cwd': str(self.checkout)}
        return verdict_of(await self.handler().handle(payload))

    async def seed(self, tasks: tuple[SeededTask, ...], *, auto_escalate: bool = False) -> None:
        section = replace(create_ticket_section(SLUG), branch=BRANCH, auto_escalate=auto_escalate)
        async with open_state(self.data_directory, self.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
                ticket_id = tickets.stage(SLUG, section, ()).id
                repository = SqliteTaskRepository(unit=entry.unit)
                for task in tasks:
                    seed_task(repository, ticket_id, task)

    def make_ticket_directory(self) -> None:
        self.checkout.joinpath('.mightymodels', str(SLUG)).mkdir(parents=True)


def seed_task(repository: SqliteTaskRepository, ticket_id: int, task: SeededTask) -> None:
    key = TaskId(task.key)
    attempt = Attempt(worker=task.worker, mode=None, owned=task.owned)
    repository.record_start(ticket_id, create_transition(key, task.before, 'in-progress'), attempt)
    if task.status != 'in-progress':
        stopped = create_transition(key, 'in-progress', task.status, reasons=task.reasons)
        repository.record_mark(ticket_id, stopped)
