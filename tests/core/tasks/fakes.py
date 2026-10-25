"""The task and attempt repositories kept in memory, over one ledger they share."""

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from mightymodels_core.tasks.errors import UnknownTaskError
from mightymodels_core.tasks.records import (
    ATTEMPT_COUNTS,
    FAILED_FIXES,
    TASKS,
    TaskRecord,
)

if TYPE_CHECKING:
    from collections.abc import Collection

    from mightymodels_core.primitives import RedactedText, TaskId
    from mightymodels_core.schemas.tasks import ArchitectMode, TaskStatus, Worker
    from mightymodels_core.tasks.records import Attempt, AttemptCounts, FailedFix, Transition

type TaskAddress = tuple[int, TaskId]


@dataclass(slots=True, kw_only=True, frozen=True)
class StartedAttempt:
    address: TaskAddress
    attempt: Attempt


@dataclass(slots=True, kw_only=True, frozen=True)
class PlacedFix:
    address: TaskAddress
    fix: FailedFix


@dataclass(slots=True, kw_only=True, frozen=True)
class PlacedTransition:
    address: TaskAddress
    transition: Transition


@dataclass(slots=True, kw_only=True, frozen=True)
class TaskLedger:
    held: dict[TaskAddress, TaskRecord] = field(default_factory=dict)
    attempts: list[StartedAttempt] = field(default_factory=list)
    fixes: list[PlacedFix] = field(default_factory=list)
    transitions: list[PlacedTransition] = field(default_factory=list)

    def tasks_of(self, ticket_id: int) -> list[TaskRecord]:
        return [task for (owner, _), task in self.held.items() if owner == ticket_id]

    def transitions_into(
        self, ticket_id: int, statuses: Collection[TaskStatus]
    ) -> list[PlacedTransition]:
        return [
            placed
            for placed in self.transitions
            if placed.address[0] == ticket_id and placed.transition.after in statuses
        ]

    def add_transition(self, address: TaskAddress, transition: Transition) -> None:
        self.transitions.append(PlacedTransition(address=address, transition=transition))


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeTaskRepository:
    ledger: TaskLedger

    def task(self, ticket_id: int, task_key: TaskId) -> TaskRecord | None:
        return self.ledger.held.get((ticket_id, task_key))

    def tasks(self, ticket_id: int) -> list[TaskRecord]:
        return self.ledger.tasks_of(ticket_id)

    def in_progress_started_by(self, ticket_id: int, worker: Worker) -> list[TaskId]:
        latest_worker: dict[TaskAddress, Worker] = {
            started.address: started.attempt.worker for started in self.ledger.attempts
        }
        return sorted(
            task.key
            for task in self.ledger.tasks_of(ticket_id)
            if task.status == 'in-progress' and latest_worker.get((ticket_id, task.key)) == worker
        )

    def record_start(self, ticket_id: int, transition: Transition, attempt: Attempt) -> None:
        address = (ticket_id, transition.task_key)
        previous = self.ledger.held.get(address)
        first_base = None if previous is None else previous.base
        self.ledger.held[address] = TaskRecord(
            key=transition.task_key,
            status=transition.after,
            owned=attempt.owned,
            base=transition.head if first_base is None else first_base,
        )
        self.ledger.attempts.append(StartedAttempt(address=address, attempt=attempt))
        self.ledger.add_transition(address, transition)
        self.refuse_too_many_tasks(ticket_id)

    def record_verification(self, ticket_id: int, transition: Transition, commit: str) -> None:
        address = (ticket_id, transition.task_key)
        held = self.ledger.held.get(address)
        if held is None:
            raise UnknownTaskError(ticket_id=ticket_id, task_key=transition.task_key)

        self.ledger.held[address] = replace(
            held, status=transition.after, commit=commit, reasons=transition.reasons
        )
        self.ledger.add_transition(address, transition)

    def record_mark(self, ticket_id: int, transition: Transition) -> None:
        address = (ticket_id, transition.task_key)
        never_started = TaskRecord(key=transition.task_key, status=transition.before)
        held = self.ledger.held.get(address) or never_started
        self.ledger.held[address] = replace(
            held, status=transition.after, reasons=transition.reasons
        )
        self.ledger.add_transition(address, transition)
        self.refuse_too_many_tasks(ticket_id)

    def refuse_too_many_tasks(self, ticket_id: int) -> None:
        held = len(self.ledger.tasks_of(ticket_id))
        if (error := TASKS.write_error(held, owner=f'ticket {ticket_id}')) is not None:
            raise error


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeAttemptRepository:
    ledger: TaskLedger

    def attempts_by_worker(self, ticket_id: int) -> AttemptCounts:
        counts: AttemptCounts = {}
        for started in self.ledger.attempts:
            owner, task_key = started.address
            if owner == ticket_id:
                by_worker = counts.setdefault(task_key, {})
                worker = started.attempt.worker
                by_worker[worker] = by_worker.get(worker, 0) + 1
        if (error := ATTEMPT_COUNTS.error(counts, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return counts

    def attempts_in_modes(
        self, ticket_id: int, task_key: TaskId, modes: Collection[ArchitectMode]
    ) -> int:
        return sum(
            started.address == (ticket_id, task_key) and started.attempt.mode in modes
            for started in self.ledger.attempts
        )

    def failed_fixes(self, ticket_id: int, task_key: TaskId) -> list[RedactedText]:
        hypotheses = [
            placed.fix.hypothesis
            for placed in self.ledger.fixes
            if placed.address == (ticket_id, task_key)
        ]
        owner = f'task {task_key} of ticket {ticket_id}'
        if (error := FAILED_FIXES.error(hypotheses, owner=owner)) is not None:
            raise error
        return hypotheses

    def record_failed_fix(self, ticket_id: int, fix: FailedFix) -> None:
        address = (ticket_id, fix.task_key)
        if address not in self.ledger.held:
            raise UnknownTaskError(ticket_id=ticket_id, task_key=fix.task_key)

        self.ledger.fixes.append(PlacedFix(address=address, fix=fix))

    def latest_transitions_into(
        self, ticket_id: int, statuses: Collection[TaskStatus], limit: int
    ) -> list[Transition]:
        into = [placed.transition for placed in self.ledger.transitions_into(ticket_id, statuses)]
        return into[max(len(into) - limit, 0) :]

    def latest_transition_of_each_task_into(
        self, ticket_id: int, statuses: Collection[TaskStatus]
    ) -> dict[TaskId, Transition]:
        latest = {
            placed.address[1]: placed.transition
            for placed in self.ledger.transitions_into(ticket_id, statuses)
        }
        if (error := TASKS.error(latest, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return latest
