from typing import TYPE_CHECKING

import pytest
from mightymodels_core.tasks import MarkRequest
from mightymodels_core.tickets import NotStagedError

from tests.core.tasks.service_builders import (
    FIRST_TASK,
    OTHER_SLUG,
    OWNED_FILE,
    SERVICE_SLUG,
    verify_as_asked,
)

if TYPE_CHECKING:
    from tests.core.tasks.service_builders import ServiceHarness


class TestShow:
    def test_show_lists_the_tasks_and_who_attempted_them(
        self, started_harness: ServiceHarness
    ) -> None:
        listing = started_harness.reads.show(SERVICE_SLUG)

        assert [record.key for record in listing.records] == [FIRST_TASK]
        assert listing.attempts == {FIRST_TASK: {'engineer': 1}}

    def test_show_lists_nothing_for_a_ticket_with_no_task(
        self, service_harness: ServiceHarness
    ) -> None:
        listing = service_harness.reads.show(SERVICE_SLUG)

        assert (listing.records, listing.attempts) == ([], {})

    def test_show_works_on_a_closed_ticket(self, started_harness: ServiceHarness) -> None:
        started_harness.tickets.seed_status(SERVICE_SLUG, 'closed')

        assert started_harness.reads.show(SERVICE_SLUG).records

    def test_show_refuses_a_ticket_that_was_never_staged(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(NotStagedError):
            service_harness.reads.show(OTHER_SLUG)


class TestReady:
    def test_ready_names_the_missing_plan_task_when_none_started(
        self, service_harness: ServiceHarness
    ) -> None:
        readiness = service_harness.reads.ready(SERVICE_SLUG)

        assert readiness.problems == ['no plan task has been started']

    def test_ready_is_clear_when_every_plan_task_is_proven_at_head(
        self, verified_harness: ServiceHarness
    ) -> None:
        readiness = verified_harness.reads.ready(SERVICE_SLUG)

        assert readiness.problems == []

    def test_ready_names_a_task_still_in_progress(self, proven_harness: ServiceHarness) -> None:
        readiness = proven_harness.reads.ready(SERVICE_SLUG)

        assert readiness.problems == [f'{FIRST_TASK} is in-progress, not verified']

    def test_ready_ignores_the_contract_commands_of_the_ticket(
        self, contracted_harness: ServiceHarness
    ) -> None:
        verify_as_asked(contracted_harness, frozenset({OWNED_FILE}))

        readiness = contracted_harness.reads.ready(SERVICE_SLUG)

        assert readiness.problems == []

    def test_ready_is_clear_for_a_superseded_task(self, started_harness: ServiceHarness) -> None:
        started_harness.service.mark(
            SERVICE_SLUG, MarkRequest(task_key=FIRST_TASK, to='superseded', reason='dropped')
        )

        readiness = started_harness.reads.ready(SERVICE_SLUG)

        assert readiness.problems == []

    def test_ready_refuses_a_ticket_that_was_never_staged(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(NotStagedError):
            service_harness.reads.ready(OTHER_SLUG)
