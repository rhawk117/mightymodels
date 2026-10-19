"""The errors of the task repositories and of the task policy."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import TaskId
    from mightymodels_core.schemas.tasks import ArchitectMode, TaskStatus


class UnknownTaskError(StateError):
    def __init__(self, *, ticket_id: int, task_key: TaskId) -> None:
        self.ticket_id = ticket_id
        self.task_key = task_key
        super().__init__(f'ticket {ticket_id} holds no task {task_key}; start the task first')


class TransitionError(StateError):
    def __init__(self, *, task_key: TaskId, current: TaskStatus, target: TaskStatus) -> None:
        self.task_key = task_key
        self.current = current
        self.target = target
        super().__init__(f'{task_key} cannot move from {current} to {target}')


class ArchitectSpentError(StateError):
    def __init__(self, *, task_key: TaskId) -> None:
        self.task_key = task_key
        super().__init__(
            f'{task_key} already had its architect recovery; route it to whats-broken, start it '
            'in systemic-refactor mode after the user approves a scope expansion, or in '
            'diagnose-replan mode for a revised contract'
        )


class InternSpentError(StateError):
    def __init__(self, *, task_key: TaskId) -> None:
        self.task_key = task_key
        super().__init__(f'{task_key} already had its intern attempt; start it by engineer')


class ModeNeedsArchitectError(StateError):
    def __init__(self, *, mode: ArchitectMode) -> None:
        self.mode = mode
        super().__init__(f'{mode} is an architect mode; start the task by architect to use it')


class TaskTooLargeError(StateError):
    def __init__(self, *, counted: str, count: int, limit: int) -> None:
        self.counted = counted
        self.count = count
        self.limit = limit
        super().__init__(
            f'{count} {counted} is over the {limit} one task may have; split the task with '
            'break-it-down, which puts the split to the user'
        )


class FixesSpentError(StateError):
    def __init__(self, *, task_key: TaskId, tried: Sequence[str]) -> None:
        self.task_key = task_key
        self.tried = tuple(tried)
        listed = ''.join(f'\n  {number}. {text}' for number, text in enumerate(tried, start=1))
        super().__init__(
            f'{task_key} is blocked: {len(tried)} fixes failed and no more are tried; report it '
            f'blocked and list the hypotheses tried, in order:{listed}\nnothing was written'
        )


class FixNotUnderwayError(StateError):
    def __init__(self, *, task_key: TaskId, current: TaskStatus) -> None:
        self.task_key = task_key
        self.current = current
        super().__init__(
            f'{task_key} is {current}; a failed fix is recorded on a task in progress, started '
            'by the dispatching primary'
        )
