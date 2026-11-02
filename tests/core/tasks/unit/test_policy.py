"""The task policy: transitions, start limits, architect-only modes, size bound and fix limit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, get_args

import pytest
from hypothesis import assume, example, given
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
    TransitionError,
    TransitionPolicy,
    VerdictPolicy,
    VerdictReasonError,
    VerdictReasonRefusedError,
    get_size_warning,
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
    ]
    return pytest.mark.parametrize(('scenario', 'reasons'), cases)


def allowed_move_cases() -> pytest.MarkDecorator:
    cases = [
        pytest.param(before, after, id=f'{before}->{after}')
        for before, after in sorted(ALLOWED_MOVES)
    ]
    return pytest.mark.parametrize(('before', 'after'), cases)


class TestTransitionPolicy:
    statuses = st.sampled_from(get_args(TaskStatus.__value__))

    def find_problem(self, before: TaskStatus, after: TaskStatus) -> TransitionError | None:
        policy = TransitionPolicy(task_key=TASK, before=before, after=after)
        return policy.get_transition_problem()

    @allowed_move_cases()
    def test_listed_transition_is_allowed(self, before: TaskStatus, after: TaskStatus) -> None:
        assert self.find_problem(before, after) is None

    @given(before=statuses, after=statuses)
    def test_unlisted_transition_is_refused(self, before: TaskStatus, after: TaskStatus) -> None:
        assume((before, after) not in ALLOWED_MOVES)

        problem = self.find_problem(before, after)

        assert isinstance(problem, TransitionError)
        assert (problem.current, problem.target) == (before, after)
        assert str(problem) == f'{TASK} cannot move from {before} to {after}'


class TestVerdictPolicy:
    failing_verdicts = st.sampled_from(['failed', 'blocked'])
    blank_reasons = st.one_of(st.none(), st.text(alphabet=' \t\n'))
    real_reasons = st.text(min_size=1).filter(lambda text: text.strip() != '')

    def find_problem(
        self, verdict: TaskStatus, reason: str | None
    ) -> VerdictReasonError | VerdictReasonRefusedError | None:
        policy = VerdictPolicy(task_key=TASK, verdict=verdict, reason=reason)
        return policy.get_reason_problem()

    @given(verdict=failing_verdicts, reason=blank_reasons)
    def test_failed_or_blocked_without_a_reason_is_refused(
        self, verdict: TaskStatus, reason: str | None
    ) -> None:
        problem = self.find_problem(verdict, reason)

        assert isinstance(problem, VerdictReasonError)
        assert problem.verdict == verdict

    @given(verdict=failing_verdicts, reason=real_reasons)
    def test_failed_or_blocked_with_a_reason_is_accepted(
        self, verdict: TaskStatus, reason: str
    ) -> None:
        assert self.find_problem(verdict, reason) is None

    @given(reason=st.text())
    def test_verified_with_a_reason_is_refused(self, reason: str) -> None:
        assert isinstance(self.find_problem('verified', reason), VerdictReasonRefusedError)

    def test_verified_without_a_reason_is_accepted(self) -> None:
        assert self.find_problem('verified', None) is None


class TestStartPolicy:
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


def size_warning_cases() -> pytest.MarkDecorator:
    sizes: list[ParameterSet] = [
        pytest.param(3, 4, False, id='three-files-four-criteria'),
        pytest.param(4, 4, True, id='four-files'),
        pytest.param(3, 5, True, id='five-criteria'),
        pytest.param(12, 6, True, id='both-over'),
    ]
    return pytest.mark.parametrize(('owned_count', 'acceptance_count', 'warns'), sizes)


class TestSizeWarning:
    @size_warning_cases()
    def test_warns_only_above_the_bounds(
        self, owned_count: int, acceptance_count: int, *, warns: bool
    ) -> None:
        warning = get_size_warning(acceptance_count=acceptance_count, owned_count=owned_count)

        assert (warning is not None) is warns

    def test_warning_names_break_it_down(self) -> None:
        warning = get_size_warning(acceptance_count=5, owned_count=4)

        assert warning is not None
        assert 'break-it-down' in warning


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
