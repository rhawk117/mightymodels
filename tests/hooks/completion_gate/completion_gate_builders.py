"""Values, payloads and the seeded state the completion gate tests share."""

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mightymodels_core.contract import Approval, ApprovedCommand, Receipt, SqliteContractRepository
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE, open_state
from mightymodels_core.primitives import TaskId, redact
from mightymodels_core.tasks import Attempt, SqliteTaskRepository, TaskRecord
from mightymodels_core.tasks.gates import GitFacts
from mightymodels_core.tickets import SqliteTicketRepository
from mightymodels_core.units_of_work import write_entry
from mightymodels_hooks.completion_gate import CompletionGateHandler, create_implementers
from mightymodels_hooks.completion_state import PlanTask, ResidualFacts

from tests.core.git.git_builders import commit_file
from tests.core.tasks.repository_builders import create_ticket_section, create_transition
from tests.hooks.dispatch.dispatch_builders import BRANCH, SLUG

if TYPE_CHECKING:
    import io
    from collections.abc import Mapping
    from pathlib import Path

    from mightymodels_core.tickets import TicketSection
    from mightymodels_core.vocabulary.contract import Outcome
    from mightymodels_core.vocabulary.tasks import Worker

    from tests.hooks.dispatch.dispatch_builders import DispatchHarness

ENGINEER = 'mightymodels:workers:engineer'
ARCHITECT = 'mightymodels:workers:architect'
INTERN = 'mightymodels:workers:intern'
OWNED = 'src/queue.py'
OUTSIDE = 'src/drain.py'
COMMAND_KEY = 'R1.AC-1'
MOMENT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
HEAD = 'a' * 40
BASE = 'b' * 40
DONE_WITH_A_COMMIT = '## ASKED\n\nthe task\n\n## DONE\n\ndid it\ncommit: 4f2a9c1\n'
DONE_WITHOUT_A_COMMIT = '## ASKED\n\nthe task\n\n## DONE\n\ndid it\n'
ASKED_ONLY = '## ASKED\n\nthe task\n'


@dataclass(slots=True, kw_only=True, frozen=True)
class SeededTask:
    key: str
    worker: Worker = 'engineer'
    owned: tuple[str, ...] = (OWNED,)


@dataclass(slots=True, kw_only=True, frozen=True)
class Reply:
    output: str | None

    @property
    def decision(self) -> str | None:
        return None if self.output is None else self.fields['decision']

    @property
    def reason(self) -> str:
        return '' if self.output is None else self.fields['reason']

    @property
    def fields(self) -> Mapping[str, str]:
        return json.loads(self.output or '{}')


def stop_payload(agent_type: str | None, *, stop_hook_active: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {'hook_event_name': 'SubagentStop'}
    payload['stop_hook_active'] = stop_hook_active
    return payload if agent_type is None else {**payload, 'agent_type': agent_type}


@dataclass(slots=True, kw_only=True, frozen=True)
class CompletionHarness:
    dispatch: DispatchHarness
    stderr: io.StringIO

    @property
    def checkout(self) -> Path:
        return self.dispatch.checkout

    def handler(self) -> CompletionGateHandler:
        environ = {PLUGIN_DATA_VARIABLE: str(self.dispatch.data_directory)}
        return CompletionGateHandler(
            environ=environ, stderr=self.stderr, implementers=create_implementers()
        )

    async def stop(self, agent_type: str | None = ENGINEER, *, active: bool = False) -> Reply:
        payload = {**stop_payload(agent_type, stop_hook_active=active), 'cwd': str(self.checkout)}
        return Reply(output=await self.handler().handle(payload))

    def write_brief(self, number: int, text: str) -> Path:
        brief = self.checkout.joinpath(
            '.mightymodels', str(SLUG), 'briefs', f'task-{number:02d}.md'
        )
        brief.parent.mkdir(parents=True, exist_ok=True)
        brief.write_text(text, encoding='utf-8')
        return brief

    async def seed(self, tasks: tuple[SeededTask, ...], *, base: str | None = None) -> None:
        section = create_ticket_section(SLUG)
        async with open_state(self.dispatch.data_directory, self.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
                ticket_id = tickets.stage(SLUG, section_on_branch(section), ()).id
                repository = SqliteTaskRepository(unit=entry.unit)
                for task in tasks:
                    attempt = Attempt(worker=task.worker, mode=None, owned=task.owned)
                    transition = create_transition(
                        TaskId(task.key), 'pending', 'in-progress', head=base
                    )
                    repository.record_start(ticket_id, transition, attempt)

    async def approve(self, key: str = COMMAND_KEY) -> None:
        async with open_state(self.dispatch.data_directory, self.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
                contracts = SqliteContractRepository(unit=entry.unit)
                command = ApprovedCommand(
                    key=key, argv=('make', 'test'), expect_exit=0, timeout=300, approved_by='user'
                )
                approval = Approval(at=MOMENT, head=BASE)
                contracts.approve(tickets.staged_ticket(SLUG).id, [command], approval)

    async def record(self, head: str, outcome: Outcome, key: str = COMMAND_KEY) -> None:
        async with open_state(self.dispatch.data_directory, self.checkout) as state:
            with write_entry(state.database, state.checkout.repository_key()) as entry:
                tickets = SqliteTicketRepository(unit=entry.unit, repository_id=entry.repository_id)
                contracts = SqliteContractRepository(unit=entry.unit)
                contracts.record(tickets.staged_ticket(SLUG).id, [receipt(head, outcome, key)])


def section_on_branch(section: TicketSection) -> TicketSection:
    return replace(section, branch=BRANCH)


def receipt(head: str, outcome: Outcome, key: str) -> Receipt:
    return Receipt(
        key=key,
        argv=('make', 'test'),
        outcome=outcome,
        exit=0 if outcome == 'pass' else 1,
        duration_ms=10,
        stdout_tail=redact(''),
        stderr_tail=redact(''),
        digest='d1',
        head=head,
        phase='task',
        at=MOMENT,
    )


def plan_task(text: str | None) -> PlanTask:
    return PlanTask(id='T1', brief='.mightymodels/port-it/briefs/task-01.md', text=text)


def residual_facts(
    *, head: str | None = HEAD, changed: frozenset[str] = frozenset(), resolves: bool = True
) -> ResidualFacts:
    task = TaskRecord(key=TaskId('R1'), status='in-progress', owned=(OWNED,), base=BASE)
    facts = GitFacts(
        head=head,
        base_resolves=resolves,
        base_is_ancestor=True,
        changed_files=changed,
        named_commit=None,
    )
    return ResidualFacts(
        task=task, commands=[], receipts={}, base_commit=BASE if resolves else None, git=facts
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ResidualScene:
    harness: CompletionHarness
    base: str

    async def start(self, key: str = 'R1', worker: Worker = 'engineer') -> None:
        task = SeededTask(key=key, worker=worker)
        await self.harness.seed((task,), base=self.base)

    async def fix(self, name: str) -> str:
        self.harness.checkout.joinpath(name).parent.mkdir(parents=True, exist_ok=True)
        return await commit_file(self.harness.checkout, name)
