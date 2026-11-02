"""The errors of the task repositories and of the task policy."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.primitives import TaskId
    from mightymodels_core.vocabulary.tasks import ArchitectMode, TaskStatus


class UnknownTaskError(StateError):
    def __init__(self, *, ticket_id: int, task_key: TaskId) -> None:
        self.ticket_id = ticket_id
        self.task_key = task_key
        super().__init__(f'ticket {ticket_id} holds no task {task_key}; start the task first')


class UndeclaredPlanTaskError(StateError):
    def __init__(self, *, task_key: TaskId) -> None:
        self.task_key = task_key
        super().__init__(
            f'{task_key} was never declared; declare the plan tasks with task_declare first'
        )


class TransitionError(StateError):
    def __init__(self, *, task_key: TaskId, current: TaskStatus, target: TaskStatus) -> None:
        self.task_key = task_key
        self.current = current
        self.target = target
        super().__init__(f'{task_key} cannot move from {current} to {target}')


class VerdictReasonError(StateError):
    def __init__(self, *, task_key: TaskId, verdict: TaskStatus) -> None:
        self.task_key = task_key
        self.verdict = verdict
        super().__init__(f'{task_key} cannot be marked {verdict} without a reason')


class VerdictReasonRefusedError(StateError):
    def __init__(self, *, task_key: TaskId) -> None:
        self.task_key = task_key
        super().__init__(f'{task_key} is verified, and a verified task takes no reason')


class ArchitectSpentError(StateError):
    def __init__(self, *, task_key: TaskId) -> None:
        self.task_key = task_key
        super().__init__(
            f'{task_key} already had its architect recovery; route it to whats-broken, start it '
            'in systemic-refactor mode after the user approves a scope expansion, or in '
            'diagnose-replan mode for a revised ASKED stanza'
        )


class InternSpentError(StateError):
    def __init__(self, *, task_key: TaskId) -> None:
        self.task_key = task_key
        super().__init__(f'{task_key} already had its intern attempt; start it by engineer')


class ModeNeedsArchitectError(StateError):
    def __init__(self, *, mode: ArchitectMode) -> None:
        self.mode = mode
        super().__init__(f'{mode} is an architect mode; start the task by architect to use it')


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


class NotPlanTaskError(StateError):
    def __init__(self, *, task_key: TaskId) -> None:
        self.task_key = task_key
        super().__init__(
            f'{task_key} is not a plan task; only plan task ids (T*) are declared, and other '
            'tasks start freely'
        )


class TaskMovedError(StateError):
    def __init__(self, *, task_key: TaskId, changed: Sequence[str]) -> None:
        self.task_key = task_key
        self.changed = tuple(changed)
        super().__init__(
            f'{task_key} changed while git was asked ({", ".join(changed)}); nothing was written, '
            'verify the task again'
        )
