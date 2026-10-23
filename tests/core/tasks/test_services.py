from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RedactedTextTooLongError
from mightymodels_core.tasks import (
    FixesSpentError,
    FixNotUnderwayError,
    MarkRequest,
    TaskOptions,
    TransitionError,
)
from mightymodels_core.tickets import ClosedTicketError

from .repository_builders import SECOND_TASK
from .service_builders import FIRST_TASK, SERVICE_SLUG

if TYPE_CHECKING:
    from .service_builders import ServiceHarness

SECRET = 'ghp_' + 'a' * 36


class TestMark:
    def test_mark_moves_a_started_task_with_its_reason(
        self, started_harness: ServiceHarness
    ) -> None:
        request = MarkRequest(task_key=FIRST_TASK, to='blocked', reason=f'needs {SECRET}')

        record = started_harness.service.mark(SERVICE_SLUG, request)

        assert record.status == 'blocked'
        assert SECRET not in ''.join(record.reasons)

    def test_mark_supersedes_a_task_that_was_never_started(
        self, service_harness: ServiceHarness
    ) -> None:
        request = MarkRequest(task_key=SECOND_TASK, to='superseded', reason='replaced')

        record = service_harness.service.mark(SERVICE_SLUG, request)

        assert (record.status, record.reasons) == ('superseded', ('replaced',))

    def test_mark_refuses_a_move_the_transitions_do_not_allow(
        self, service_harness: ServiceHarness
    ) -> None:
        request = MarkRequest(task_key=SECOND_TASK, to='verified', reason='no')

        with pytest.raises(TransitionError):
            service_harness.service.mark(SERVICE_SLUG, request)

    def test_mark_refuses_a_closed_ticket(self, started_harness: ServiceHarness) -> None:
        started_harness.tickets.seed_status(SERVICE_SLUG, 'closed')
        request = MarkRequest(task_key=FIRST_TASK, to='failed', reason='no')

        with pytest.raises(ClosedTicketError):
            started_harness.service.mark(SERVICE_SLUG, request)


class TestRecordFailedFix:
    at_limit = 'a' * TaskOptions().hypothesis_limit
    over_limit = at_limit + 'a'

    def test_a_failed_fix_is_recorded_redacted_with_the_fixes_left(
        self, started_harness: ServiceHarness
    ) -> None:
        recorded = started_harness.service.record_failed_fix(
            SERVICE_SLUG, FIRST_TASK, f'the key {SECRET} was stale'
        )

        assert (recorded.number, recorded.remaining) == (1, 2)
        assert SECRET not in recorded.hypothesis
        assert started_harness.attempts.failed_fixes(started_harness.ticket_id, FIRST_TASK) == [
            recorded.hypothesis
        ]

    def test_a_hypothesis_over_the_limit_is_refused_and_nothing_is_stored(
        self, started_harness: ServiceHarness
    ) -> None:
        with pytest.raises(RedactedTextTooLongError):
            started_harness.service.record_failed_fix(SERVICE_SLUG, FIRST_TASK, self.over_limit)

        assert started_harness.attempts.failed_fixes(started_harness.ticket_id, FIRST_TASK) == []

    def test_a_hypothesis_at_the_limit_is_recorded(self, started_harness: ServiceHarness) -> None:
        recorded = started_harness.service.record_failed_fix(
            SERVICE_SLUG, FIRST_TASK, self.at_limit
        )

        assert recorded.hypothesis == self.at_limit

    def test_a_failed_fix_is_refused_on_a_task_that_is_not_in_progress(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(FixNotUnderwayError):
            service_harness.service.record_failed_fix(SERVICE_SLUG, FIRST_TASK, 'a guess')

    def test_the_fourth_failed_fix_is_refused_and_lists_the_three_tried(
        self, started_harness: ServiceHarness
    ) -> None:
        service = started_harness.service
        for guess in ('one', 'two', 'three'):
            service.record_failed_fix(SERVICE_SLUG, FIRST_TASK, guess)

        with pytest.raises(FixesSpentError) as refused:
            service.record_failed_fix(SERVICE_SLUG, FIRST_TASK, 'four')

        assert refused.value.tried == ('one', 'two', 'three')

    def test_a_failed_fix_is_refused_on_a_closed_ticket(
        self, started_harness: ServiceHarness
    ) -> None:
        started_harness.tickets.seed_status(SERVICE_SLUG, 'closed')

        with pytest.raises(ClosedTicketError):
            started_harness.service.record_failed_fix(SERVICE_SLUG, FIRST_TASK, 'a guess')
