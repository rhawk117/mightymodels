"""The task policy: transitions, start limits, architect-only modes, size bound and fix limit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, get_args

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from mightymodels_core.primitives import TaskId
from mightymodels_core.tasks import (
    ArchitectSpentError,
    FixesSpentError,
    FixNotUnderwayError,
    FixPolicy,
    InternSpentError,
    ModeNeedsArchitectError,
    StartPolicy,
    TaskTooLargeError,
    TransitionError,
    TransitionPolicy,
)
from mightymodels_core.vocabulary.tasks import TaskStatus

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.schemas.tasks import ArchitectMode, Worker

TASK = TaskId('T7')
ALLOWED_MOVES: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset({
    ('pending', 'in-progress'),
    ('pending', 'superseded'),
    ('in-progress', 'verified'),
    ('in-progress', 'failed'),
    ('in-progress', 'blocked'),
    ('in-progress', 'superseded'),
    ('failed', 'in-progress'),
    ('failed', 'superseded'),
    ('blocked', 'in-progress'),
    ('blocked', 'superseded'),
})


@dataclass(slots=True, kw_only=True, frozen=True)
class StartScenario:
    name: str
    worker: Worker = 'engineer'
    mode: ArchitectMode | None = None
    before: TaskStatus = 'pending'
    attempts: tuple[tuple[Worker, int], ...] = ()
    implementation_spent: int = 0
    acceptance_count: int = 2
    owned_count: int = 2
    too_large_approved: bool = False
    problem: type[Exception] | None = None
    marks: tuple[pytest.MarkDecorator, ...] = ()

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name, marks=self.marks)

    @property
    def policy(self) -> StartPolicy:
        return StartPolicy(
            task_key=TASK,
            before=self.before,
            worker=self.worker,
            mode=self.mode,
            attempts=dict(self.attempts),
            implementation_spent=self.implementation_spent,
            acceptance_count=self.acceptance_count,
            owned_count=self.owned_count,
            too_large_approved=self.too_large_approved,
        )


def start_accepted_cases() -> pytest.MarkDecorator:
    scenarios = [
        StartScenario(name='engineer-from-pending'),
        StartScenario(name='engineer-restarts-failed', before='failed'),
        StartScenario(name='engineer-restarts-blocked', before='blocked'),
        StartScenario(name='intern-first-attempt', worker='intern'),
        StartScenario(name='intern-after-engineer', worker='intern', attempts=(('engineer', 3),)),
        StartScenario(name='architect-defaults-to-recovery', worker='architect'),
        StartScenario(
            name='architect-diagnose-replan-is-unlimited',
            worker='architect',
            mode='diagnose-replan',
            implementation_spent=5,
        ),
        StartScenario(
            name='architect-systemic-refactor-gets-a-second-pass',
            worker='architect',
            mode='systemic-refactor',
            implementation_spent=1,
        ),
        StartScenario(
            name='architect-systemic-refactor-restarts-in-progress',
            worker='architect',
            mode='systemic-refactor',
            before='in-progress',
        ),
        StartScenario(name='acceptance-at-the-bound', acceptance_count=4),
        StartScenario(name='owned-at-the-bound', owned_count=10),
        StartScenario(
            name='over-the-bound-with-user-approval',
            acceptance_count=9,
            owned_count=30,
            too_large_approved=True,
        ),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def start_refused_cases() -> pytest.MarkDecorator:
    scenarios = [
        StartScenario(
            name='engineer-mode-needs-architect',
            mode='recovery-implementation',
            problem=ModeNeedsArchitectError,
        ),
        StartScenario(
            name='intern-mode-needs-architect',
            worker='intern',
            mode='diagnose-replan',
            problem=ModeNeedsArchitectError,
        ),
        StartScenario(
            name='acceptance-over-the-bound', acceptance_count=5, problem=TaskTooLargeError
        ),
        StartScenario(name='owned-over-the-bound', owned_count=11, problem=TaskTooLargeError),
        StartScenario(
            name='second-architect-recovery',
            worker='architect',
            implementation_spent=1,
            problem=ArchitectSpentError,
        ),
        StartScenario(
            name='second-explicit-recovery',
            worker='architect',
            mode='recovery-implementation',
            implementation_spent=1,
            problem=ArchitectSpentError,
        ),
        StartScenario(
            name='third-systemic-refactor',
            worker='architect',
            mode='systemic-refactor',
            implementation_spent=2,
            problem=ArchitectSpentError,
        ),
        StartScenario(
            name='second-intern-attempt',
            worker='intern',
            attempts=(('intern', 1),),
            problem=InternSpentError,
        ),
        StartScenario(name='verified-task-restart', before='verified', problem=TransitionError),
        StartScenario(name='superseded-task-restart', before='superseded', problem=TransitionError),
        StartScenario(name='in-progress-restart', before='in-progress', problem=TransitionError),
        StartScenario(
            name='recovery-cannot-restart-in-progress',
            worker='architect',
            before='in-progress',
            problem=TransitionError,
        ),
    ]
    return pytest.mark.parametrize('scenario', [scenario.param for scenario in scenarios])


def start_reasons_cases() -> pytest.MarkDecorator:
    cases = [
        pytest.param(StartScenario(name='engineer'), ('by engineer',), id='engineer'),
        pytest.param(
            StartScenario(name='architect', worker='architect'),
            ('by architect', 'in recovery-implementation mode'),
            id='architect-default-mode',
        ),
        pytest.param(
            StartScenario(name='approved', too_large_approved=True),
            ('by engineer', 'too large, approved by user'),
            id='too-large-approved',
        ),
    ]
    return pytest.mark.parametrize(('scenario', 'reasons'), cases)


class TestTransitionPolicy:
    statuses = st.sampled_from(get_args(TaskStatus.__value__))

    def find_problem(self, before: TaskStatus, after: TaskStatus) -> TransitionError | None:
        policy = TransitionPolicy(task_key=TASK, before=before, after=after)
        return policy.get_transition_problem()

    @given(before=statuses, after=statuses)
    @example(before='pending', after='in-progress')
    @example(before='pending', after='superseded')
    @example(before='in-progress', after='verified')
    @example(before='in-progress', after='failed')
    @example(before='in-progress', after='blocked')
    @example(before='in-progress', after='superseded')
    @example(before='failed', after='in-progress')
    @example(before='failed', after='superseded')
    @example(before='blocked', after='in-progress')
    @example(before='blocked', after='superseded')
    def test_transition_is_allowed_exactly_when_listed(
        self, before: TaskStatus, after: TaskStatus
    ) -> None:
        problem = self.find_problem(before, after)

        if (before, after) in ALLOWED_MOVES:
            assert problem is None
            return

        assert isinstance(problem, TransitionError)
        assert (problem.current, problem.target) == (before, after)
        assert str(problem) == f'{TASK} cannot move from {before} to {after}'


class TestStartPolicy:
    @pytest.fixture
    def oversized_owned(self) -> StartScenario:
        return StartScenario(name='big', owned_count=11)

    @start_accepted_cases()
    def test_start_is_accepted(self, scenario: StartScenario) -> None:
        assert scenario.policy.get_start_problem() is None

    @start_refused_cases()
    def test_start_is_refused_with_its_own_error(self, scenario: StartScenario) -> None:
        problem = scenario.policy.get_start_problem()

        assert type(problem) is scenario.problem

    @start_reasons_cases()
    def test_start_records_its_reasons(
        self, scenario: StartScenario, reasons: tuple[str, ...]
    ) -> None:
        assert scenario.policy.reasons == reasons

    def test_size_problem_names_what_is_counted(self, oversized_owned: StartScenario) -> None:
        problem = oversized_owned.policy.get_size_problem()

        assert isinstance(problem, TaskTooLargeError)
        assert (problem.counted, problem.count, problem.limit) == ('owned files', 11, 10)


class TestFixPolicy:
    statuses_outside_in_progress = st.sampled_from([
        status for status in get_args(TaskStatus.__value__) if status != 'in-progress'
    ])
    tries_under_the_limit = st.lists(st.text(), max_size=2).map(tuple)

    @pytest.fixture
    def spent_tries(self) -> tuple[str, ...]:
        return ('one', 'two', 'three')

    def find_problem(
        self, before: TaskStatus, tried: tuple[str, ...]
    ) -> FixNotUnderwayError | FixesSpentError | None:
        return FixPolicy(task_key=TASK, before=before, tried=tried).get_fix_problem()

    @given(before=statuses_outside_in_progress)
    @example(before='pending')
    @example(before='verified')
    @example(before='failed')
    @example(before='blocked')
    @example(before='superseded')
    def test_fix_outside_in_progress_is_refused(self, before: TaskStatus) -> None:
        assert isinstance(self.find_problem(before, ()), FixNotUnderwayError)

    @given(tried=tries_under_the_limit)
    @example(tried=())
    @example(tried=('one', 'two'))
    def test_fix_under_the_limit_is_accepted(self, tried: tuple[str, ...]) -> None:
        assert self.find_problem('in-progress', tried) is None

    def test_third_failed_fix_spends_the_limit(self, spent_tries: tuple[str, ...]) -> None:
        problem = self.find_problem('in-progress', spent_tries)

        assert isinstance(problem, FixesSpentError)
        assert problem.tried == spent_tries
        assert '1. one\n  2. two\n  3. three' in str(problem)
