from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.tasks import (
    ArchitectSpentError,
    InternSpentError,
    MarkRequest,
    ModeNeedsArchitectError,
    TaskOptions,
    TaskRecord,
    TransitionError,
)
from mightymodels_core.tickets import ClosedTicketError, NotStagedError

from tests.core.tasks.service_builders import (
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

    from tests.core.tasks.service_builders import ServiceHarness


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
    return pytest.mark.parametrize('refused', [mode_needs_architect.param])


class TestStart:
    def test_start_records_an_in_progress_task_with_the_base_and_sorted_owned_files(
        self, declared_harness: ServiceHarness
    ) -> None:
        request = create_start_request(owned=('src/b.py', OWNED_FILE, OWNED_FILE))

        record = declared_harness.service.start(SERVICE_SLUG, request)

        assert (record.status, record.base) == ('in-progress', BASE_COMMIT)
        assert record.owned == (OWNED_FILE, 'src/b.py')

    def test_start_moves_the_ticket_in_progress(self, declared_harness: ServiceHarness) -> None:
        declared_harness.service.start(SERVICE_SLUG, create_start_request())

        assert declared_harness.tickets.staged_ticket(SERVICE_SLUG).status == 'in-progress'

    def test_start_records_who_started_it(self, declared_harness: ServiceHarness) -> None:
        declared_harness.service.start(SERVICE_SLUG, create_start_request())

        counts = declared_harness.attempts.attempts_by_worker(declared_harness.ticket_id)
        assert counts == {FIRST_TASK: {'engineer': 1}}

    def test_start_notes_the_worker_in_the_transition_reasons(
        self, declared_harness: ServiceHarness
    ) -> None:
        declared_harness.service.start(SERVICE_SLUG, create_start_request())

        [placed] = declared_harness.task_ledger.transitions
        assert placed.transition.reasons == ('by engineer',)

    @start_refusal_cases()
    def test_start_refuses_a_request_the_policy_refuses(
        self, declared_harness: ServiceHarness, refused: RefusedStart
    ) -> None:
        with pytest.raises(refused.error_type):
            declared_harness.service.start(SERVICE_SLUG, refused.request)

        assert declared_harness.tasks.tasks(declared_harness.ticket_id) == [
            TaskRecord(key=FIRST_TASK, status='pending')
        ]

    def test_start_refuses_a_task_that_is_verified(
        self, verified_task_harness: ServiceHarness
    ) -> None:
        with pytest.raises(TransitionError):
            verified_task_harness.service.start(SERVICE_SLUG, create_start_request())

    def test_start_refuses_an_intern_that_already_tried(
        self, declared_harness: ServiceHarness
    ) -> None:
        service = declared_harness.service
        intern = create_start_request(worker='intern')
        service.start(SERVICE_SLUG, intern)
        service.mark(SERVICE_SLUG, MarkRequest(task_key=FIRST_TASK, to='failed', reason='no'))

        with pytest.raises(InternSpentError):
            service.start(SERVICE_SLUG, intern)

    def test_start_refuses_a_second_architect_recovery(
        self, declared_harness: ServiceHarness
    ) -> None:
        service = declared_harness.service
        architect = create_start_request(worker='architect', mode='recovery-implementation')
        service.start(SERVICE_SLUG, architect)
        service.mark(SERVICE_SLUG, MarkRequest(task_key=FIRST_TASK, to='failed', reason='no'))

        with pytest.raises(ArchitectSpentError):
            service.start(SERVICE_SLUG, architect)

    def test_start_refuses_a_ticket_that_was_never_staged(
        self, declared_harness: ServiceHarness
    ) -> None:
        with pytest.raises(NotStagedError):
            declared_harness.service.start(OTHER_SLUG, create_start_request())

    def test_start_refuses_a_closed_ticket(self, declared_harness: ServiceHarness) -> None:
        declared_harness.tickets.seed_status(SERVICE_SLUG, 'closed')

        with pytest.raises(ClosedTicketError):
            declared_harness.service.start(SERVICE_SLUG, create_start_request())


class TestSizeWarning:
    def test_a_configured_owned_limit_moves_the_size_warning(
        self, declared_harness: ServiceHarness
    ) -> None:
        strict = replace(declared_harness.service, options=TaskOptions(warn_owned_above=0))
        request = create_start_request()

        assert strict.get_size_warning(request)
        assert declared_harness.service.get_size_warning(request) is None

    def test_a_configured_acceptance_limit_moves_the_size_warning(
        self, declared_harness: ServiceHarness
    ) -> None:
        strict = replace(declared_harness.service, options=TaskOptions(warn_acceptance_above=0))
        request = create_start_request(acceptance_count=1)

        assert strict.get_size_warning(request)
