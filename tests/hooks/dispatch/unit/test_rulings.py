import io
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.edge import PLUGIN_DATA_VARIABLE
from mightymodels_core.primitives import StateError
from mightymodels_hooks.branch_state import BranchTickets, StartedTask
from mightymodels_hooks.cli import REFUSED, HookCommand, create_hook_router
from mightymodels_hooks.workers import PHASE_AGENTS, agent_type

from tests.hooks.dispatch.dispatch_builders import SLUG, FakeStartedTasks, judge, one_ticket

if TYPE_CHECKING:
    from collections.abc import Sequence

    from _pytest.mark import ParameterSet

ENGINEER = agent_type('engineer')
ARCHITECT = agent_type('architect')
INTERN = agent_type('intern')
AGENT_ID = 'agent-1'
IMPLEMENTATION = 'mightymodels:implementation'
UNREADABLE = StateError('the database is locked')


def started(*owned_counts: int) -> tuple[StartedTask, ...]:
    return tuple(
        StartedTask(id=f'T{number}', owned=tuple(f'f{index}.py' for index in range(count)))
        for number, count in enumerate(owned_counts, start=1)
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class WorkerDispatch:
    name: str
    caller: str
    target: object
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)


def worker_dispatch_inside_row_cases() -> pytest.MarkDecorator:
    bare_name = WorkerDispatch(
        name='engineer-bare-name', caller=agent_type('engineer'), target='code-scout'
    )
    qualified_name = WorkerDispatch(
        name='engineer-qualified-name',
        caller=agent_type('engineer'),
        target=agent_type('code-scout'),
    )
    merge_vader = WorkerDispatch(
        name='merge-vader-web-scout', caller=agent_type('merge-vader'), target='web-scout'
    )
    uncle_bob = WorkerDispatch(
        name='uncle-bob-qualitylens', caller=agent_type('uncle-bob'), target='qualitylens'
    )
    return pytest.mark.parametrize(
        'dispatch', [bare_name.param, qualified_name.param, merge_vader.param, uncle_bob.param]
    )


def worker_dispatch_outside_row_cases() -> pytest.MarkDecorator:
    wingman = WorkerDispatch(
        name='engineer-wingman', caller=agent_type('engineer'), target='wingman'
    )
    scout_to_scout = WorkerDispatch(
        name='scout-code-scout', caller=agent_type('code-scout'), target='code-scout'
    )
    uncle_bob = WorkerDispatch(
        name='uncle-bob-web-scout', caller=agent_type('uncle-bob'), target='web-scout'
    )
    unknown_caller = WorkerDispatch(
        name='unknown-caller', caller='mightymodels:workers:nobody', target='code-scout'
    )
    no_target = WorkerDispatch(name='no-target', caller=agent_type('engineer'), target=None)
    return pytest.mark.parametrize(
        'dispatch',
        [
            wingman.param,
            scout_to_scout.param,
            uncle_bob.param,
            unknown_caller.param,
            no_target.param,
        ],
    )


def idle_target_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('target', [ENGINEER, ARCHITECT, 'engineer'])


def outside_caller_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('caller', ['Explore', 'other-plugin:agent', 'mightymodels'])


def intern_tasks_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'tasks',
        [
            pytest.param((), id='none'),
            pytest.param(started(2), id='two'),
            pytest.param(started(1, 3), id='mixed'),
            pytest.param(started(0), id='zero'),
        ],
    )


def phase_target_cases() -> pytest.MarkDecorator:
    targets = [f'{prefix}{phase}' for phase in PHASE_AGENTS for prefix in ('', 'mightymodels:')]
    return pytest.mark.parametrize('target', targets)


def phase_caller_cases() -> pytest.MarkDecorator:
    callers = [
        pytest.param((None, None), id='plain-main-thread'),
        pytest.param((IMPLEMENTATION, None), id='phase-main-thread'),
        pytest.param((ENGINEER, AGENT_ID), id='engineer'),
        pytest.param((agent_type('code-scout'), AGENT_ID), id='code-scout'),
        pytest.param((agent_type('merge-vader'), AGENT_ID), id='merge-vader'),
    ]
    return pytest.mark.parametrize('caller', callers)


def unreadable_stdin_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize(
        'stdin', ['', 'not json', '[1, 2]', '"agent_type": "mightymodels:']
    )


class TestWorkerCallers:
    @worker_dispatch_inside_row_cases()
    async def test_dispatch_inside_the_row_is_not_judged(self, dispatch: WorkerDispatch) -> None:
        assert (
            await judge(dispatch.target, caller=dispatch.caller, agent_id=AGENT_ID)
        ).decision is None

    @worker_dispatch_outside_row_cases()
    async def test_dispatch_outside_the_row_is_denied(self, dispatch: WorkerDispatch) -> None:
        assert (
            await judge(dispatch.target, caller=dispatch.caller, agent_id=AGENT_ID)
        ).decision == 'deny'

    async def test_worker_dispatch_reads_no_state(self) -> None:
        fake = FakeStartedTasks()
        await judge('code-scout', fake, caller=ENGINEER, agent_id=AGENT_ID)
        assert fake.reads == []


class TestAgentId:
    @pytest.mark.parametrize('target', ['code-scout', ENGINEER, ARCHITECT])
    async def test_phase_agent_type_without_agent_id_gets_no_roster_refusal(
        self, target: str
    ) -> None:
        fake = FakeStartedTasks(tickets=one_ticket(in_progress=('T1',)))
        assert (await judge(target, fake, caller=IMPLEMENTATION)).decision is None

    @pytest.mark.parametrize('target', [ENGINEER, ARCHITECT])
    async def test_phase_main_thread_gets_the_started_task_ruling_of_a_plain_session(
        self, target: str
    ) -> None:
        fake = FakeStartedTasks(tickets=one_ticket())
        plain = await judge(target, fake)
        phase = await judge(target, fake, caller=IMPLEMENTATION)
        assert (plain.decision, phase) == ('deny', plain)

    async def test_worker_with_agent_id_is_held_to_its_row(self) -> None:
        verdict = await judge('wingman', caller=ENGINEER, agent_id=AGENT_ID)
        assert (verdict.decision, ENGINEER in verdict.detail) == ('deny', True)

    async def test_unknown_plugin_type_with_agent_id_is_refused(self) -> None:
        verdict = await judge('code-scout', caller=IMPLEMENTATION, agent_id=AGENT_ID)
        assert verdict.decision == 'deny'


class TestPhaseTargets:
    @phase_target_cases()
    @phase_caller_cases()
    async def test_phase_agent_is_refused_as_a_target(
        self, target: str, caller: tuple[str | None, str | None]
    ) -> None:
        agent, agent_id = caller
        assert (await judge(target, caller=agent, agent_id=agent_id)).decision == 'deny'


class TestMainThreadStartedTask:
    @idle_target_cases()
    async def test_dispatch_with_no_task_in_progress_is_denied_whatever_the_prompt_claims(
        self, target: str
    ) -> None:
        fake = FakeStartedTasks(tickets=one_ticket())
        verdict = await judge(target, fake)
        assert (verdict.decision, SLUG in verdict.detail) == ('deny', True)

    async def test_dispatch_with_a_task_in_progress_is_not_judged(self) -> None:
        fake = FakeStartedTasks(tickets=one_ticket(in_progress=('T1',)))
        assert (await judge(ENGINEER, fake)).decision is None

    async def test_dispatch_with_no_unclosed_ticket_is_not_judged(self) -> None:
        assert (await judge(ENGINEER)).decision is None

    async def test_dispatch_with_several_tickets_shows_one_line(self) -> None:
        fake = FakeStartedTasks(tickets=BranchTickets(unclosed=('one', 'two')))
        verdict = await judge(ENGINEER, fake)
        assert (verdict.decision, 'one, two' in verdict.detail) == ('message', True)

    async def test_dispatch_with_unreadable_tickets_is_denied(self) -> None:
        verdict = await judge(ENGINEER, FakeStartedTasks(tickets=UNREADABLE))
        assert (verdict.decision, 'locked' in verdict.detail) == ('deny', True)

    @outside_caller_cases()
    async def test_caller_outside_the_plugin_is_the_main_thread(self, caller: str) -> None:
        fake = FakeStartedTasks(tickets=one_ticket())
        assert (await judge(ENGINEER, fake, caller=caller)).decision == 'deny'

    async def test_dispatch_of_another_worker_reads_no_state(self) -> None:
        fake = FakeStartedTasks()
        await judge('code-scout', fake)
        assert fake.reads == []


class TestEscalation:
    async def test_architect_denial_names_the_missing_task(self) -> None:
        assert (await judge(ARCHITECT, FakeStartedTasks(tickets=one_ticket()))).decision == 'deny'

    async def test_wingman_is_not_judged(self) -> None:
        fake = FakeStartedTasks(tickets=one_ticket(in_progress=('T1',)))
        assert (await judge('wingman', fake)).decision is None


class TestIntern:
    @intern_tasks_cases()
    async def test_intern_is_denied_unless_its_task_owns_exactly_one_file(
        self, tasks: Sequence[StartedTask]
    ) -> None:
        verdict = await judge(INTERN, FakeStartedTasks(started=tuple(tasks)))
        assert (verdict.decision, ENGINEER in verdict.detail) == ('deny', True)

    async def test_intern_with_one_file_is_not_judged(self) -> None:
        assert (await judge('intern', FakeStartedTasks(started=started(1, 1)))).decision is None

    async def test_intern_with_unreadable_started_tasks_is_denied(self) -> None:
        verdict = await judge(INTERN, FakeStartedTasks(started=UNREADABLE))
        assert (verdict.decision, 'locked' in verdict.detail) == ('deny', True)


class TestUnreadableInput:
    async def run_dispatch(self, stdin: str) -> tuple[int, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        router = create_hook_router({PLUGIN_DATA_VARIABLE: '/nowhere'}, stderr)
        command = HookCommand(router=router, stdin=io.StringIO(stdin), stdout=stdout, stderr=stderr)
        return await command.run(['dispatch-hook']), stdout.getvalue()

    @unreadable_stdin_cases()
    async def test_unreadable_stdin_exits_two_with_no_ruling(self, stdin: str) -> None:
        assert await self.run_dispatch(stdin) == (REFUSED, '')
