"""Every attempt repository case runs against the sqlite store and the fake."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import ReadLimitError, redact
from mightymodels_core.tasks import AttemptRepository, FailedFix, UnknownTaskError
from mightymodels_core.tasks.tests.fakes import FakeAttemptRepository, TaskLedger

from .repository_builders import SECOND_TASK, create_attempt, create_transition
from .service_builders import FIRST_TASK

if TYPE_CHECKING:
    from .repository_builders import TaskHarness

RECOVERY = replace(create_attempt(), worker='architect', mode='recovery-implementation')
REFACTOR = replace(create_attempt(), worker='architect', mode='systemic-refactor')


def create_fix(hypothesis: str, *, day: int = 4) -> FailedFix:
    return FailedFix(
        task_key=FIRST_TASK, hypothesis=redact(hypothesis), at=datetime(2026, 1, day, tzinfo=UTC)
    )


class TestImplementations:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeAttemptRepository(ledger=TaskLedger()), AttemptRepository)

    def test_repository_satisfies_the_protocol(self, harness: TaskHarness) -> None:
        assert isinstance(harness.attempts, AttemptRepository)


class TestAttempts:
    @pytest.fixture
    def attempted(self, harness: TaskHarness) -> TaskHarness:
        first = create_transition(FIRST_TASK, 'pending', 'in-progress')
        retry = create_transition(FIRST_TASK, 'failed', 'in-progress', day=3)
        other = create_transition(SECOND_TASK, 'pending', 'in-progress', day=4)
        harness.tasks.record_start(harness.ticket_id, first, create_attempt())
        harness.tasks.record_start(harness.ticket_id, retry, RECOVERY)
        harness.tasks.record_start(harness.ticket_id, other, create_attempt())
        return harness

    def test_attempts_are_counted_by_task_and_worker(self, attempted: TaskHarness) -> None:
        counts = attempted.attempts.attempts_by_worker(attempted.ticket_id)

        assert counts == {
            FIRST_TASK: {'engineer': 1, 'architect': 1},
            SECOND_TASK: {'engineer': 1},
        }

    def test_attempts_of_another_ticket_are_not_counted(self, attempted: TaskHarness) -> None:
        assert attempted.attempts.attempts_by_worker(attempted.other_ticket_id) == {}

    def test_attempts_in_the_modes_are_counted(self, attempted: TaskHarness) -> None:
        in_modes = attempted.attempts.attempts_in_modes(
            attempted.ticket_id, FIRST_TASK, ['recovery-implementation', 'systemic-refactor']
        )

        assert in_modes == 1

    def test_attempts_outside_the_modes_are_not_counted(self, attempted: TaskHarness) -> None:
        in_modes = attempted.attempts.attempts_in_modes(
            attempted.ticket_id, FIRST_TASK, ['diagnose-replan']
        )

        assert in_modes == 0

    def test_attempts_of_a_task_that_never_started_are_zero(self, harness: TaskHarness) -> None:
        in_modes = harness.attempts.attempts_in_modes(
            harness.ticket_id, FIRST_TASK, ['recovery-implementation']
        )

        assert in_modes == 0


class TestFailedFixes:
    first = create_fix('the cache is stale')
    second = create_fix('the lock is not released', day=5)

    @pytest.fixture
    def started(self, harness: TaskHarness) -> TaskHarness:
        start = create_transition(FIRST_TASK, 'pending', 'in-progress')
        harness.tasks.record_start(harness.ticket_id, start, create_attempt())
        return harness

    @pytest.fixture
    def fixed(self, started: TaskHarness) -> TaskHarness:
        started.attempts.record_failed_fix(started.ticket_id, self.first)
        started.attempts.record_failed_fix(started.ticket_id, self.second)
        return started

    @pytest.fixture
    def overspent(self, fixed: TaskHarness) -> TaskHarness:
        for number in range(2):
            fixed.attempts.record_failed_fix(fixed.ticket_id, create_fix(f'guess {number}'))
        return fixed

    def test_failed_fixes_are_empty_before_any_is_recorded(self, started: TaskHarness) -> None:
        assert started.attempts.failed_fixes(started.ticket_id, FIRST_TASK) == []

    def test_failed_fixes_come_back_in_the_order_recorded(self, fixed: TaskHarness) -> None:
        hypotheses = fixed.attempts.failed_fixes(fixed.ticket_id, FIRST_TASK)

        assert hypotheses == [self.first.hypothesis, self.second.hypothesis]

    def test_failed_fixes_of_a_task_that_never_started_are_empty(
        self, harness: TaskHarness
    ) -> None:
        assert harness.attempts.failed_fixes(harness.ticket_id, FIRST_TASK) == []

    def test_fix_for_a_task_that_never_started_is_refused(self, harness: TaskHarness) -> None:
        with pytest.raises(UnknownTaskError):
            harness.attempts.record_failed_fix(harness.ticket_id, self.first)

    def test_reading_more_failed_fixes_than_the_limit_is_refused(
        self, overspent: TaskHarness
    ) -> None:
        with pytest.raises(ReadLimitError):
            overspent.attempts.failed_fixes(overspent.ticket_id, FIRST_TASK)


class TestTransitions:
    @pytest.fixture
    def moved(self, harness: TaskHarness) -> TaskHarness:
        moves = [
            create_transition(FIRST_TASK, 'pending', 'in-progress', day=2),
            create_transition(SECOND_TASK, 'pending', 'in-progress', day=3),
        ]
        for move in moves:
            harness.tasks.record_start(harness.ticket_id, move, create_attempt())
        harness.tasks.record_mark(
            harness.ticket_id,
            create_transition(FIRST_TASK, 'in-progress', 'blocked', day=4, reasons=('stuck',)),
        )
        harness.tasks.record_verification(
            harness.ticket_id,
            create_transition(SECOND_TASK, 'in-progress', 'verified', day=5),
            'fff0001',
        )
        harness.tasks.record_mark(
            harness.ticket_id,
            create_transition(FIRST_TASK, 'blocked', 'blocked', day=6, reasons=('still stuck',)),
        )
        return harness

    def test_latest_transitions_come_back_oldest_first(self, moved: TaskHarness) -> None:
        into = moved.attempts.latest_transitions_into(
            moved.ticket_id, ['blocked', 'verified'], limit=10
        )

        assert [(move.task_key, move.at.day) for move in into] == [
            (FIRST_TASK, 4),
            (SECOND_TASK, 5),
            (FIRST_TASK, 6),
        ]

    def test_latest_transitions_keep_the_newest_within_the_limit(self, moved: TaskHarness) -> None:
        into = moved.attempts.latest_transitions_into(
            moved.ticket_id, ['blocked', 'verified'], limit=2
        )

        assert [move.at.day for move in into] == [5, 6]

    def test_latest_transitions_read_back_as_written(self, moved: TaskHarness) -> None:
        (move,) = moved.attempts.latest_transitions_into(moved.ticket_id, ['verified'], limit=1)

        assert move == create_transition(SECOND_TASK, 'in-progress', 'verified', day=5)

    def test_latest_transitions_of_another_ticket_are_not_read(self, moved: TaskHarness) -> None:
        into = moved.attempts.latest_transitions_into(
            moved.other_ticket_id, ['blocked', 'verified'], limit=10
        )

        assert into == []

    def test_latest_transition_of_each_task_is_kept_once(self, moved: TaskHarness) -> None:
        latest = moved.attempts.latest_transition_of_each_task_into(
            moved.ticket_id, ['blocked', 'verified']
        )

        assert {key: move.at.day for key, move in latest.items()} == {
            FIRST_TASK: 6,
            SECOND_TASK: 5,
        }

    def test_latest_transition_of_each_task_reads_back_the_reasons(
        self, moved: TaskHarness
    ) -> None:
        latest = moved.attempts.latest_transition_of_each_task_into(moved.ticket_id, ['blocked'])

        assert latest[FIRST_TASK].reasons == (redact('still stuck'),)
