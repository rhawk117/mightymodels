"""Declaring plan tasks writes them as pending rows and never touches an existing one."""

from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import TaskId
from mightymodels_core.tasks import TaskRecord, get_readiness_problems
from mightymodels_core.tasks.errors import NotPlanTaskError

from tests.core.tasks.repository_builders import SECOND_TASK, create_attempt, create_transition
from tests.core.tasks.service_builders import (
    FIRST_TASK,
    SERVICE_MOMENT,
    SERVICE_SLUG,
    create_start_request,
)

if TYPE_CHECKING:
    from tests.core.tasks.repository_builders import TaskHarness
    from tests.core.tasks.service_builders import ServiceHarness


class TestDeclareInTheSqliteRepository:
    def test_declared_ids_become_pending_rows(self, harness: TaskHarness) -> None:
        harness.tasks.declare(harness.ticket_id, [FIRST_TASK, SECOND_TASK], SERVICE_MOMENT)

        assert harness.tasks.tasks(harness.ticket_id) == [
            TaskRecord(key=FIRST_TASK, status='pending'),
            TaskRecord(key=SECOND_TASK, status='pending'),
        ]

    def test_declaring_writes_no_transition(self, harness: TaskHarness) -> None:
        harness.tasks.declare(harness.ticket_id, [FIRST_TASK], SERVICE_MOMENT)

        transitions = harness.attempts.latest_transitions_into(
            harness.ticket_id, ['pending', 'in-progress', 'verified'], 10
        )
        assert transitions == []

    def test_declaring_twice_changes_nothing(self, harness: TaskHarness) -> None:
        harness.tasks.declare(harness.ticket_id, [FIRST_TASK], SERVICE_MOMENT)
        before = harness.tasks.tasks(harness.ticket_id)

        harness.tasks.declare(harness.ticket_id, [FIRST_TASK], SERVICE_MOMENT)

        assert harness.tasks.tasks(harness.ticket_id) == before

    def test_declaring_leaves_an_in_progress_task_as_it_was(self, harness: TaskHarness) -> None:
        start = create_transition(FIRST_TASK, 'pending', 'in-progress')
        harness.tasks.record_start(harness.ticket_id, start, create_attempt())
        before = harness.tasks.task(harness.ticket_id, FIRST_TASK)

        harness.tasks.declare(harness.ticket_id, [FIRST_TASK], SERVICE_MOMENT)

        assert harness.tasks.task(harness.ticket_id, FIRST_TASK) == before
        assert before is not None
        assert before.status == 'in-progress'

    def test_declaring_leaves_a_verified_task_as_it_was(self, harness: TaskHarness) -> None:
        start = create_transition(FIRST_TASK, 'pending', 'in-progress')
        harness.tasks.record_start(harness.ticket_id, start, create_attempt())
        done = create_transition(FIRST_TASK, 'in-progress', 'verified', day=3)
        harness.tasks.record_verification(harness.ticket_id, done, 'def5678')
        before = harness.tasks.task(harness.ticket_id, FIRST_TASK)

        harness.tasks.declare(harness.ticket_id, [FIRST_TASK], SERVICE_MOMENT)

        assert harness.tasks.task(harness.ticket_id, FIRST_TASK) == before
        assert before is not None
        assert before.status == 'verified'

    def test_a_declared_task_starts_as_in_progress(self, harness: TaskHarness) -> None:
        harness.tasks.declare(harness.ticket_id, [FIRST_TASK], SERVICE_MOMENT)
        start = create_transition(FIRST_TASK, 'pending', 'in-progress')

        harness.tasks.record_start(harness.ticket_id, start, create_attempt())

        task = harness.tasks.task(harness.ticket_id, FIRST_TASK)
        assert task is not None
        assert task.status == 'in-progress'
        assert task.base == 'abc1234'

    def test_a_declared_unstarted_task_blocks_readiness(self, harness: TaskHarness) -> None:
        harness.tasks.declare(harness.ticket_id, [FIRST_TASK], SERVICE_MOMENT)

        problems = get_readiness_problems(harness.tasks.tasks(harness.ticket_id))

        assert any(FIRST_TASK in problem for problem in problems)


class TestDeclareInTheService:
    def test_declare_returns_the_ticket_tasks_as_pending(
        self, service_harness: ServiceHarness
    ) -> None:
        records = service_harness.service.declare(SERVICE_SLUG, [FIRST_TASK, SECOND_TASK])

        assert records == [
            TaskRecord(key=FIRST_TASK, status='pending'),
            TaskRecord(key=SECOND_TASK, status='pending'),
        ]

    @pytest.mark.parametrize('task_key', ['R1', 'C2'])
    def test_declare_refuses_a_task_that_is_not_a_plan_task(
        self, service_harness: ServiceHarness, task_key: str
    ) -> None:
        with pytest.raises(NotPlanTaskError):
            service_harness.service.declare(SERVICE_SLUG, [FIRST_TASK, TaskId(task_key)])

        assert service_harness.tasks.tasks(service_harness.ticket_id) == []

    def test_a_declared_task_can_be_started(self, service_harness: ServiceHarness) -> None:
        service_harness.service.declare(SERVICE_SLUG, [FIRST_TASK])

        started = service_harness.service.start(SERVICE_SLUG, create_start_request())

        assert started.status == 'in-progress'
