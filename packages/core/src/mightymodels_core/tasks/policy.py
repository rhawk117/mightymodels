"""Every rule a task start, mark or failed fix is refused by, computed from values passed in.

The caller fetches the task's status, its attempt counts and the fixes tried, asks a policy and
raises the verdict it returns. A policy reads no repository and no clock.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.tasks.errors import (
    ArchitectSpentError,
    FixesSpentError,
    FixNotUnderwayError,
    InternSpentError,
    ModeNeedsArchitectError,
    TaskTooLargeError,
    TransitionError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mightymodels_core.primitives import TaskId
    from mightymodels_core.vocabulary.tasks import ArchitectMode, TaskStatus, Worker

type Transitions = dict[TaskStatus, frozenset[TaskStatus]]
type StartProblem = (
    ModeNeedsArchitectError
    | TaskTooLargeError
    | ArchitectSpentError
    | InternSpentError
    | TransitionError
)

IMPLEMENTATION_MODES: frozenset[ArchitectMode] = frozenset({
    'recovery-implementation',
    'systemic-refactor',
})


def create_transitions() -> Transitions:
    return {
        'pending': frozenset({'in-progress', 'superseded'}),
        'in-progress': frozenset({'verified', 'failed', 'blocked', 'superseded'}),
        'failed': frozenset({'in-progress', 'superseded'}),
        'blocked': frozenset({'in-progress', 'superseded'}),
        'verified': frozenset(),
        'superseded': frozenset(),
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskOptions:
    intern_limit: int = 1
    architect_limit: int = 1
    failed_fix_limit: int = 3
    acceptance_limit: int = 4
    owned_limit: int = 10
    hypothesis_limit: int = 4000
    transitions: Transitions = field(default_factory=create_transitions)


@dataclass(slots=True, kw_only=True, frozen=True)
class TransitionPolicy:
    task_key: TaskId
    before: TaskStatus
    after: TaskStatus
    options: TaskOptions = field(default_factory=TaskOptions)

    @property
    def is_allowed(self) -> bool:
        return self.after in self.options.transitions[self.before]

    def get_transition_problem(self) -> TransitionError | None:
        if self.is_allowed:
            return None

        return TransitionError(task_key=self.task_key, current=self.before, target=self.after)


@dataclass(slots=True, kw_only=True, frozen=True)
class StartPolicy:
    task_key: TaskId
    before: TaskStatus
    worker: Worker
    mode: ArchitectMode | None
    attempts: Mapping[Worker, int]
    implementation_spent: int
    acceptance_count: int
    owned_count: int
    too_large_approved: bool = False
    options: TaskOptions = field(default_factory=TaskOptions)

    @property
    def architect_mode(self) -> ArchitectMode | None:
        if self.worker != 'architect':
            return None

        return self.mode or 'recovery-implementation'

    @property
    def is_expanded(self) -> bool:
        return self.architect_mode == 'systemic-refactor'

    @property
    def architect_limit(self) -> int:
        return self.options.architect_limit + int(self.is_expanded)

    @property
    def is_architect_spent(self) -> bool:
        return (
            self.architect_mode in IMPLEMENTATION_MODES
            and self.implementation_spent >= self.architect_limit
        )

    @property
    def is_intern_spent(self) -> bool:
        return (
            self.worker == 'intern' and self.attempts.get('intern', 0) >= self.options.intern_limit
        )

    @property
    def is_restart_allowed(self) -> bool:
        reaches = TransitionPolicy(
            task_key=self.task_key, before=self.before, after='in-progress', options=self.options
        )
        return reaches.is_allowed or (self.is_expanded and self.before == 'in-progress')

    @property
    def reasons(self) -> tuple[str, ...]:
        mode_reason = () if self.architect_mode is None else (f'in {self.architect_mode} mode',)
        approval = ('too large, approved by user',) if self.too_large_approved else ()
        return (f'by {self.worker}', *mode_reason, *approval)

    def get_mode_problem(self) -> ModeNeedsArchitectError | None:
        if self.worker == 'architect' or self.mode is None:
            return None

        return ModeNeedsArchitectError(mode=self.mode)

    def get_size_problem(self) -> TaskTooLargeError | None:
        if self.too_large_approved:
            return None

        if self.acceptance_count > self.options.acceptance_limit:
            return TaskTooLargeError(
                counted='acceptance criteria',
                count=self.acceptance_count,
                limit=self.options.acceptance_limit,
            )

        if self.owned_count > self.options.owned_limit:
            return TaskTooLargeError(
                counted='owned files', count=self.owned_count, limit=self.options.owned_limit
            )

        return None

    def get_start_problem(self) -> StartProblem | None:
        if problem := self.get_mode_problem():
            return problem

        if problem := self.get_size_problem():
            return problem

        if self.is_architect_spent:
            return ArchitectSpentError(task_key=self.task_key)

        if self.is_intern_spent:
            return InternSpentError(task_key=self.task_key)

        if not self.is_restart_allowed:
            return TransitionError(
                task_key=self.task_key, current=self.before, target='in-progress'
            )

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class FixPolicy:
    task_key: TaskId
    before: TaskStatus
    tried: Sequence[str]
    options: TaskOptions = field(default_factory=TaskOptions)

    @property
    def is_underway(self) -> bool:
        return self.before == 'in-progress'

    @property
    def is_spent(self) -> bool:
        return len(self.tried) >= self.options.failed_fix_limit

    def get_fix_problem(self) -> FixNotUnderwayError | FixesSpentError | None:
        if not self.is_underway:
            return FixNotUnderwayError(task_key=self.task_key, current=self.before)

        if self.is_spent:
            return FixesSpentError(task_key=self.task_key, tried=self.tried)

        return None
