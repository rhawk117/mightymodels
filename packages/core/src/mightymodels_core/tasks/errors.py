"""The errors of the task repositories."""

from typing import TYPE_CHECKING

from mightymodels_core.primitives import StateError

if TYPE_CHECKING:
    from mightymodels_core.primitives import TaskId


class UnknownTaskError(StateError):
    def __init__(self, *, ticket_id: int, task_key: TaskId) -> None:
        self.ticket_id = ticket_id
        self.task_key = task_key
        super().__init__(f'ticket {ticket_id} holds no task {task_key}; start the task first')
