from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.tasks import (
    ArchitectSpentError,
    InternSpentError,
    MarkRequest,
    ModeNeedsArchitectError,
    TaskTooLargeError,
    TransitionError,
)
from mightymodels_core.tickets import ClosedTicketError, NotStagedError

from .service_builders import (
    BASE_COMMIT,
    FIRST_TASK,
    OTHER_SLUG,
    OWNED_FILE,
    SERVICE_SLUG,
    create_start_request,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.tasks import StartRequest

    from .service_builders import ServiceHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedStart:
    name: str
    request: StartRequest
    error_type: type[Exception]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def start_refusal_cases() -> pytest.MarkDecorator:
    mode_needs_architect = RefusedStart(
        name='mode-needs-architect',
        request=create_start_request(mode='systemic-refactor'),
        error_type=ModeNeedsArchitectError,
    )
    too_large = RefusedStart(
        name='too-large',
        request=create_start_request(acceptance_count=5),
        error_type=TaskTooLargeError,
    )
    return pytest.mark.parametrize('refused', [mode_needs_architect.param, too_large.param])


class TestStart:
    def test_start_records_an_in_progress_task_with_the_base_and_sorted_owned_files(
        self, service_harness: ServiceHarness
    ) -> None:
        request = create_start_request(owned=('src/b.py', OWNED_FILE, OWNED_FILE))

        record = service_harness.service.start(SERVICE_SLUG, request)

        assert (record.status, record.base) == ('in-progress', BASE_COMMIT)
        assert record.owned == (OWNED_FILE, 'src/b.py')

    def test_start_moves_the_ticket_in_progress(self, service_harness: ServiceHarness) -> None:
        service_harness.service.start(SERVICE_SLUG, create_start_request())

        assert service_harness.tickets.staged_ticket(SERVICE_SLUG).status == 'in-progress'

    def test_start_records_who_started_it(self, service_harness: ServiceHarness) -> None:
        service_harness.service.start(SERVICE_SLUG, create_start_request())

        counts = service_harness.attempts.attempts_by_worker(service_harness.ticket_id)
        assert counts == {FIRST_TASK: {'engineer': 1}}

    def test_start_notes_the_worker_in_the_transition_reasons(
        self, service_harness: ServiceHarness
    ) -> None:
        service_harness.service.start(SERVICE_SLUG, create_start_request())

        [placed] = service_harness.task_ledger.transitions
        assert placed.transition.reasons == ('by engineer',)

    @start_refusal_cases()
    def test_start_refuses_a_request_the_policy_refuses(
        self, service_harness: ServiceHarness, refused: RefusedStart
    ) -> None:
        with pytest.raises(refused.error_type):
            service_harness.service.start(SERVICE_SLUG, refused.request)

        assert service_harness.tasks.tasks(service_harness.ticket_id) == []

    def test_start_refuses_a_task_that_is_verified(self, verified_harness: ServiceHarness) -> None:
        with pytest.raises(TransitionError):
            verified_harness.service.start(SERVICE_SLUG, create_start_request())

    def test_start_refuses_an_intern_that_already_tried(
        self, service_harness: ServiceHarness
    ) -> None:
        service = service_harness.service
        intern = create_start_request(worker='intern')
        service.start(SERVICE_SLUG, intern)
        service.mark(SERVICE_SLUG, MarkRequest(task_key=FIRST_TASK, to='failed', reason='no'))

        with pytest.raises(InternSpentError):
            service.start(SERVICE_SLUG, intern)

    def test_start_refuses_a_second_architect_recovery(
        self, service_harness: ServiceHarness
    ) -> None:
        service = service_harness.service
        architect = create_start_request(worker='architect', mode='recovery-implementation')
        service.start(SERVICE_SLUG, architect)
        service.mark(SERVICE_SLUG, MarkRequest(task_key=FIRST_TASK, to='failed', reason='no'))

        with pytest.raises(ArchitectSpentError):
            service.start(SERVICE_SLUG, architect)

    def test_start_refuses_a_ticket_that_was_never_staged(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(NotStagedError):
            service_harness.service.start(OTHER_SLUG, create_start_request())

    def test_start_refuses_a_closed_ticket(self, service_harness: ServiceHarness) -> None:
        service_harness.tickets.seed_status(SERVICE_SLUG, 'closed')

        with pytest.raises(ClosedTicketError):
            service_harness.service.start(SERVICE_SLUG, create_start_request())
