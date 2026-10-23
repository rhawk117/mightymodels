from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import MissingParentError
from mightymodels_core.schemas.tasks import (
    ADD_TASK_ATTEMPT,
    ADD_TASK_FAILED_FIX,
    ADD_TASK_TRANSITION,
    ATTEMPTS_BY_WORKER,
    ATTEMPTS_IN_MODES,
    IN_PROGRESS_TASKS_STARTED_BY,
    LATEST_TRANSITION_OF_EACH_TASK_INTO,
    LATEST_TRANSITIONS_INTO,
    RECORD_TASK_VERIFICATION,
    TASK_BY_KEY,
    TASK_COUNT,
    TASK_FAILED_FIXES,
    TASKS_OF_TICKET,
    UPSERT_TASK,
    AddTaskAttemptParams,
    AddTaskFailedFixParams,
    AddTaskTransitionParams,
    AttemptsInModesParams,
    RecordTaskVerificationParams,
    StartedByParams,
    TaskFailedFixesParams,
    TaskKeyParams,
    TicketTaskCountParams,
    TicketTasksParams,
    TransitionsIntoParams,
    UpsertTaskParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database
    from mightymodels_core.schemas.tasks import ArchitectMode, TaskStatus, Worker

pytestmark = pytest.mark.integration

STARTED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER = datetime(2026, 1, 2, 3, 5, 6, tzinfo=UTC)


def upsert(
    ticket_id: int,
    task_key: str,
    status: TaskStatus = 'in-progress',
    base: str | None = 'base1',
) -> UpsertTaskParams:
    return UpsertTaskParams(
        ticket_id=ticket_id,
        task_key=task_key,
        status=status,
        owned=['src/a.py'],
        base=base,
        commit=None,
        reasons=[],
        updated_at=STARTED_AT,
    )


def start(database: Database, params: UpsertTaskParams) -> int:
    with database.write() as unit:
        started = unit.one(UPSERT_TASK, params)
    assert started is not None
    return started.id


def attempt(
    task_id: int, worker: Worker, mode: ArchitectMode | None = None
) -> AddTaskAttemptParams:
    return AddTaskAttemptParams(task_id=task_id, worker=worker, mode=mode, at=STARTED_AT)


def transition(task_id: int, before: TaskStatus, after: TaskStatus) -> AddTaskTransitionParams:
    return AddTaskTransitionParams(
        task_id=task_id, before=before, after=after, reasons=['why'], head='abc', at=STARTED_AT
    )


class TestTasks:
    def test_a_started_task_reads_back_by_key(self, database: Database, ticket_id: int) -> None:
        start(database, upsert(ticket_id, 'T1'))

        with database.read() as unit:
            task = unit.one(TASK_BY_KEY, TaskKeyParams(ticket_id=ticket_id, task_key='T1'))
            missing = unit.one(TASK_BY_KEY, TaskKeyParams(ticket_id=ticket_id, task_key='T9'))

        assert task is not None
        assert task.status == 'in-progress'
        assert task.owned == ['src/a.py']
        assert task.base == 'base1'
        assert task.commit is None
        assert task.reasons == []
        assert task.updated_at == STARTED_AT
        assert missing is None

    def test_restarting_keeps_the_first_base_and_the_task_id(
        self, database: Database, ticket_id: int
    ) -> None:
        first = start(database, upsert(ticket_id, 'T1', base='base1'))
        again = start(database, upsert(ticket_id, 'T1', base='base2'))

        with database.read() as unit:
            task = unit.one(TASK_BY_KEY, TaskKeyParams(ticket_id=ticket_id, task_key='T1'))

        assert again == first
        assert task is not None
        assert task.base == 'base1'

    def test_a_mark_before_any_start_has_no_base(self, database: Database, ticket_id: int) -> None:
        start(database, upsert(ticket_id, 'T1', status='blocked', base=None))

        with database.read() as unit:
            task = unit.one(TASK_BY_KEY, TaskKeyParams(ticket_id=ticket_id, task_key='T1'))

        assert task is not None
        assert task.base is None

    def test_tasks_list_in_creation_order_and_count(
        self, database: Database, ticket_id: int
    ) -> None:
        for key in ('T2', 'T1', 'T3'):
            start(database, upsert(ticket_id, key))

        with database.read() as unit:
            tasks = unit.all(TASKS_OF_TICKET, TicketTasksParams(ticket_id=ticket_id, limit=2))
            count = unit.one(TASK_COUNT, TicketTaskCountParams(ticket_id=ticket_id))

        assert [task.task_key for task in tasks] == ['T2', 'T1']
        assert count is not None
        assert count.count == 3

    def test_verification_updates_the_task_and_reports_whether_it_matched(
        self, database: Database, ticket_id: int
    ) -> None:
        task_id = start(database, upsert(ticket_id, 'T1'))

        def verify(task_key: str) -> int | None:
            params = RecordTaskVerificationParams(
                ticket_id=ticket_id,
                task_key=task_key,
                status='verified',
                commit='deadbeef',
                reasons=['ok'],
                updated_at=LATER,
            )
            with database.write() as unit:
                recorded = unit.one(RECORD_TASK_VERIFICATION, params)
            return None if recorded is None else recorded.id

        assert verify('T1') == task_id
        assert verify('T9') is None
        with database.read() as unit:
            task = unit.one(TASK_BY_KEY, TaskKeyParams(ticket_id=ticket_id, task_key='T1'))
        assert task is not None
        assert task.status == 'verified'
        assert task.commit == 'deadbeef'
        assert task.reasons == ['ok']
        assert task.updated_at == LATER

    def test_a_task_needs_a_ticket(self, database: Database) -> None:
        with pytest.raises(MissingParentError), database.write() as unit:
            unit.one(UPSERT_TASK, upsert(999, 'T1'))


class TestStartedBy:
    def test_only_in_progress_tasks_whose_latest_attempt_is_by_the_worker_are_listed(
        self, database: Database, ticket_id: int
    ) -> None:
        first = start(database, upsert(ticket_id, 'T1'))
        second = start(database, upsert(ticket_id, 'T2'))
        third = start(database, upsert(ticket_id, 'T3', status='verified'))
        with database.write() as unit:
            unit.run(ADD_TASK_ATTEMPT, attempt(first, 'engineer'))
            unit.run(ADD_TASK_ATTEMPT, attempt(first, 'architect'))
            unit.run(ADD_TASK_ATTEMPT, attempt(second, 'engineer'))
            unit.run(ADD_TASK_ATTEMPT, attempt(third, 'engineer'))

        with database.read() as unit:
            engineers = unit.all(
                IN_PROGRESS_TASKS_STARTED_BY,
                StartedByParams(ticket_id=ticket_id, worker='engineer', limit=10),
            )
            architects = unit.all(
                IN_PROGRESS_TASKS_STARTED_BY,
                StartedByParams(ticket_id=ticket_id, worker='architect', limit=10),
            )

        assert [row.task_key for row in engineers] == ['T2']
        assert [row.task_key for row in architects] == ['T1']


class TestAttempts:
    def test_attempts_are_counted_per_task_and_worker_in_first_attempt_order(
        self, database: Database, ticket_id: int
    ) -> None:
        first = start(database, upsert(ticket_id, 'T1'))
        second = start(database, upsert(ticket_id, 'T2'))
        with database.write() as unit:
            unit.run(ADD_TASK_ATTEMPT, attempt(second, 'engineer'))
            unit.run(ADD_TASK_ATTEMPT, attempt(first, 'engineer'))
            unit.run(ADD_TASK_ATTEMPT, attempt(second, 'engineer'))
            unit.run(ADD_TASK_ATTEMPT, attempt(second, 'architect'))

        with database.read() as unit:
            counts = unit.all(ATTEMPTS_BY_WORKER, TicketTasksParams(ticket_id=ticket_id, limit=10))

        assert [(row.task_key, row.worker, row.attempts) for row in counts] == [
            ('T2', 'engineer', 2),
            ('T1', 'engineer', 1),
            ('T2', 'architect', 1),
        ]

    def test_attempts_in_modes_counts_only_the_listed_modes(
        self, database: Database, ticket_id: int
    ) -> None:
        task_id = start(database, upsert(ticket_id, 'T1'))
        with database.write() as unit:
            unit.run(ADD_TASK_ATTEMPT, attempt(task_id, 'engineer'))
            unit.run(ADD_TASK_ATTEMPT, attempt(task_id, 'architect', 'diagnose-replan'))
            unit.run(
                ADD_TASK_ATTEMPT,
                attempt(task_id, 'architect', 'systemic-refactor'),
            )

        def count(modes: list[ArchitectMode]) -> int:
            with database.read() as unit:
                row = unit.one(
                    ATTEMPTS_IN_MODES, AttemptsInModesParams(task_id=task_id, modes=modes)
                )
            assert row is not None
            return row.count

        assert count(['diagnose-replan', 'systemic-refactor']) == 2
        assert count(['recovery-implementation']) == 0
        assert count([]) == 0


class TestFailedFixes:
    def test_failed_fixes_list_in_record_order_up_to_the_limit(
        self, database: Database, ticket_id: int
    ) -> None:
        task_id = start(database, upsert(ticket_id, 'T1'))
        with database.write() as unit:
            for hypothesis in ('one', 'two', 'three', 'four'):
                unit.run(
                    ADD_TASK_FAILED_FIX,
                    AddTaskFailedFixParams(task_id=task_id, hypothesis=hypothesis, at=STARTED_AT),
                )

        with database.read() as unit:
            fixes = unit.all(TASK_FAILED_FIXES, TaskFailedFixesParams(task_id=task_id, limit=3))

        assert [fix.hypothesis for fix in fixes] == ['one', 'two', 'three']

    def test_a_failed_fix_needs_its_task(self, database: Database) -> None:
        params = AddTaskFailedFixParams(task_id=999, hypothesis='x', at=STARTED_AT)
        with pytest.raises(MissingParentError), database.write() as unit:
            unit.run(ADD_TASK_FAILED_FIX, params)


@pytest.mark.usefixtures('recorded')
class TestTransitions:
    @pytest.fixture
    def recorded(self, database: Database, ticket_id: int) -> None:
        first = start(database, upsert(ticket_id, 'T1'))
        second = start(database, upsert(ticket_id, 'T2'))
        with database.write() as unit:
            unit.run(ADD_TASK_TRANSITION, transition(first, 'pending', 'in-progress'))
            unit.run(ADD_TASK_TRANSITION, transition(second, 'pending', 'in-progress'))
            unit.run(ADD_TASK_TRANSITION, transition(first, 'in-progress', 'failed'))
            unit.run(ADD_TASK_TRANSITION, transition(first, 'failed', 'in-progress'))

    def test_latest_transitions_into_are_newest_first_and_limited(
        self, database: Database, ticket_id: int
    ) -> None:
        params = TransitionsIntoParams(ticket_id=ticket_id, statuses=['in-progress'], limit=2)
        with database.read() as unit:
            rows = unit.all(LATEST_TRANSITIONS_INTO, params)

        assert [(row.task_key, row.before) for row in rows] == [
            ('T1', 'failed'),
            ('T2', 'pending'),
        ]
        assert rows[0].after == 'in-progress'
        assert rows[0].reasons == ['why']
        assert rows[0].head == 'abc'
        assert rows[0].at == STARTED_AT

    def test_the_latest_transition_of_each_task_into_a_status_is_one_row_per_task(
        self, database: Database, ticket_id: int
    ) -> None:
        params = TransitionsIntoParams(
            ticket_id=ticket_id, statuses=['in-progress', 'failed'], limit=10
        )
        with database.read() as unit:
            rows = unit.all(LATEST_TRANSITION_OF_EACH_TASK_INTO, params)

        assert sorted((row.task_key, row.before) for row in rows) == [
            ('T1', 'failed'),
            ('T2', 'pending'),
        ]

    def test_no_statuses_match_nothing(self, database: Database, ticket_id: int) -> None:
        params = TransitionsIntoParams(ticket_id=ticket_id, statuses=[], limit=10)
        with database.read() as unit:
            assert unit.all(LATEST_TRANSITIONS_INTO, params) == []
            assert unit.all(LATEST_TRANSITION_OF_EACH_TASK_INTO, params) == []
