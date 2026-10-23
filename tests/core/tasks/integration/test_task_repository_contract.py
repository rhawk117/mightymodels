"""Every task repository case runs against the sqlite store and the fake."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import TaskId, WriteLimitError, redact
from mightymodels_core.tasks import TaskRecord, TaskRepository, UnknownTaskError
from mightymodels_core.tasks.records import TASKS
from mightymodels_core.tasks.tests.fakes import FakeTaskRepository, TaskLedger

from tests.core.tasks.repository_builders import SECOND_TASK, create_attempt, create_transition
from tests.core.tasks.service_builders import FIRST_TASK

if TYPE_CHECKING:
    from tests.core.tasks.repository_builders import TaskHarness


class TestImplementations:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeTaskRepository(ledger=TaskLedger()), TaskRepository)

    def test_repository_satisfies_the_protocol(self, harness: TaskHarness) -> None:
        assert isinstance(harness.tasks, TaskRepository)


class TestRecordStart:
    start = create_transition(FIRST_TASK, 'pending', 'in-progress', reasons=('picked up',))
    attempt = create_attempt(owned=('src/a.py', 'src/b.py'))

    @pytest.fixture
    def started(self, harness: TaskHarness) -> TaskHarness:
        harness.tasks.record_start(harness.ticket_id, self.start, self.attempt)
        return harness

    def test_task_is_none_before_any_start(self, harness: TaskHarness) -> None:
        assert harness.tasks.task(harness.ticket_id, FIRST_TASK) is None

    def test_tasks_are_empty_before_any_start(self, harness: TaskHarness) -> None:
        assert harness.tasks.tasks(harness.ticket_id) == []

    def test_started_task_is_read_back_without_the_start_reasons(
        self, started: TaskHarness
    ) -> None:
        expected = TaskRecord(
            key=FIRST_TASK,
            status='in-progress',
            owned=('src/a.py', 'src/b.py'),
            base='abc1234',
        )

        assert started.tasks.task(started.ticket_id, FIRST_TASK) == expected

    def test_restart_keeps_the_first_base_and_takes_the_new_owned_files(
        self, started: TaskHarness
    ) -> None:
        restart = create_transition(FIRST_TASK, 'failed', 'in-progress', day=3, head='def5678')

        started.tasks.record_start(started.ticket_id, restart, create_attempt(owned=('src/c.py',)))

        task = started.tasks.task(started.ticket_id, FIRST_TASK)
        assert task is not None
        assert (task.base, task.owned) == ('abc1234', ('src/c.py',))

    def test_tasks_come_back_in_start_order(self, started: TaskHarness) -> None:
        second = create_transition(SECOND_TASK, 'pending', 'in-progress')

        started.tasks.record_start(started.ticket_id, second, self.attempt)

        keys = [task.key for task in started.tasks.tasks(started.ticket_id)]
        assert keys == [FIRST_TASK, SECOND_TASK]

    def test_tasks_of_another_ticket_are_not_read(self, started: TaskHarness) -> None:
        assert started.tasks.tasks(started.other_ticket_id) == []
        assert started.tasks.task(started.other_ticket_id, FIRST_TASK) is None


class TestInProgressStartedBy:
    start = create_transition(FIRST_TASK, 'pending', 'in-progress')

    @pytest.fixture
    def engineer_started(self, harness: TaskHarness) -> TaskHarness:
        harness.tasks.record_start(harness.ticket_id, self.start, create_attempt())
        return harness

    def test_task_is_listed_under_the_worker_that_started_it(
        self, engineer_started: TaskHarness
    ) -> None:
        listed = engineer_started.tasks.in_progress_started_by(
            engineer_started.ticket_id, 'engineer'
        )

        assert listed == [FIRST_TASK]

    def test_task_is_not_listed_under_another_worker(self, engineer_started: TaskHarness) -> None:
        listed = engineer_started.tasks.in_progress_started_by(
            engineer_started.ticket_id, 'architect'
        )

        assert listed == []

    def test_latest_attempt_decides_the_worker(self, engineer_started: TaskHarness) -> None:
        recovery = replace(create_attempt(), worker='architect', mode='recovery-implementation')
        retry = create_transition(FIRST_TASK, 'in-progress', 'in-progress', day=3)

        engineer_started.tasks.record_start(engineer_started.ticket_id, retry, recovery)

        tasks = engineer_started.tasks
        assert tasks.in_progress_started_by(engineer_started.ticket_id, 'engineer') == []
        assert tasks.in_progress_started_by(engineer_started.ticket_id, 'architect') == [FIRST_TASK]

    def test_task_that_left_in_progress_is_not_listed(self, engineer_started: TaskHarness) -> None:
        verified = create_transition(FIRST_TASK, 'in-progress', 'verified', day=3)
        engineer_started.tasks.record_verification(engineer_started.ticket_id, verified, 'fff0001')

        listed = engineer_started.tasks.in_progress_started_by(
            engineer_started.ticket_id, 'engineer'
        )

        assert listed == []


class TestRecordVerification:
    start = create_transition(FIRST_TASK, 'pending', 'in-progress')
    verification = create_transition(
        FIRST_TASK, 'in-progress', 'verified', day=3, reasons=('tests pass',)
    )

    @pytest.fixture
    def started(self, harness: TaskHarness) -> TaskHarness:
        harness.tasks.record_start(harness.ticket_id, self.start, create_attempt())
        return harness

    def test_verification_sets_status_commit_and_reasons(self, started: TaskHarness) -> None:
        started.tasks.record_verification(started.ticket_id, self.verification, 'fff0001')

        expected = TaskRecord(
            key=FIRST_TASK,
            status='verified',
            owned=('src/a.py',),
            base='abc1234',
            commit='fff0001',
            reasons=(redact('tests pass'),),
        )
        assert started.tasks.task(started.ticket_id, FIRST_TASK) == expected

    def test_verifying_a_task_that_never_started_is_refused(self, harness: TaskHarness) -> None:
        with pytest.raises(UnknownTaskError):
            harness.tasks.record_verification(harness.ticket_id, self.verification, 'fff0001')


class TestRecordMark:
    start = create_transition(FIRST_TASK, 'pending', 'in-progress')
    mark = create_transition(
        FIRST_TASK, 'in-progress', 'blocked', day=3, reasons=('waiting on review',)
    )

    @pytest.fixture
    def started(self, harness: TaskHarness) -> TaskHarness:
        harness.tasks.record_start(harness.ticket_id, self.start, create_attempt())
        return harness

    def test_mark_keeps_what_the_task_held(self, started: TaskHarness) -> None:
        started.tasks.record_mark(started.ticket_id, self.mark)

        expected = TaskRecord(
            key=FIRST_TASK,
            status='blocked',
            owned=('src/a.py',),
            base='abc1234',
            reasons=(redact('waiting on review'),),
        )
        assert started.tasks.task(started.ticket_id, FIRST_TASK) == expected

    def test_mark_of_a_task_that_never_started_creates_it(self, harness: TaskHarness) -> None:
        superseded = create_transition(FIRST_TASK, 'pending', 'superseded', reasons=('replaced',))

        harness.tasks.record_mark(harness.ticket_id, superseded)

        expected = TaskRecord(key=FIRST_TASK, status='superseded', reasons=(redact('replaced'),))
        assert harness.tasks.task(harness.ticket_id, FIRST_TASK) == expected


class TestTaskCap:
    held_tasks = TASKS.rows

    @pytest.fixture
    def full_harness(self, harness: TaskHarness) -> TaskHarness:
        for number in range(self.held_tasks):
            start = create_transition(TaskId(f'T{number}'), 'pending', 'in-progress')
            harness.tasks.record_start(harness.ticket_id, start, create_attempt())
        return harness

    def test_start_past_the_cap_is_refused(self, full_harness: TaskHarness) -> None:
        start = create_transition(TaskId('T-over'), 'pending', 'in-progress')

        with pytest.raises(WriteLimitError):
            full_harness.tasks.record_start(full_harness.ticket_id, start, create_attempt())

    def test_mark_past_the_cap_is_refused(self, full_harness: TaskHarness) -> None:
        mark = create_transition(TaskId('T-over'), 'pending', 'superseded')

        with pytest.raises(WriteLimitError):
            full_harness.tasks.record_mark(full_harness.ticket_id, mark)

    def test_tasks_at_the_cap_are_read_back(self, full_harness: TaskHarness) -> None:
        assert len(full_harness.tasks.tasks(full_harness.ticket_id)) == self.held_tasks
