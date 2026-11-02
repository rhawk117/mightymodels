from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.tasks import (
    MarkRequest,
    TaskMovedError,
    TransitionError,
    VerdictReasonError,
    VerdictReasonRefusedError,
    VerifyRequest,
)
from mightymodels_core.tickets import ClosedTicketError

from tests.core.tasks.service_builders import (
    BASE_COMMIT,
    DONE_COMMIT,
    FIRST_TASK,
    OWNED_FILE,
    SERVICE_SLUG,
    create_git_facts,
    create_verdict,
    create_verify_request,
    verify_as_asked,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks import TaskRecord, VerifyVerdict

    from tests.core.tasks.service_builders import ServiceHarness

OUTSIDE_FILE = 'src/elsewhere.py'
OWNED_CHANGE = frozenset({OWNED_FILE})


@dataclass(slots=True, kw_only=True, frozen=True)
class Movement:
    name: str
    moved: str
    status: TaskStatus = 'in-progress'
    base: str = BASE_COMMIT
    owned: tuple[str, ...] = (OWNED_FILE,)

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def verify_movement_cases() -> pytest.MarkDecorator:
    status = Movement(name='status', moved='status', status='blocked')
    base = Movement(name='base', moved='base', base='other01')
    owned = Movement(name='owned-set', moved='owned set', owned=(OWNED_FILE, 'src/b.py'))
    return pytest.mark.parametrize('movement', [status.param, base.param, owned.param])


def verdict_cases() -> pytest.MarkDecorator:
    return pytest.mark.parametrize('verdict', ['failed', 'blocked'])


class TestPrepareVerification:
    def test_prepare_returns_the_task_git_is_asked_about(
        self, started_harness: ServiceHarness
    ) -> None:
        task = started_harness.service.prepare_verification(SERVICE_SLUG, create_verdict())

        assert (task.base, task.owned) == (BASE_COMMIT, (OWNED_FILE,))

    def test_prepare_refuses_a_task_that_was_never_started(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(TransitionError):
            service_harness.service.prepare_verification(SERVICE_SLUG, create_verdict())

    def test_prepare_refuses_a_task_that_cannot_move_to_verified(
        self, started_harness: ServiceHarness
    ) -> None:
        started_harness.service.mark(
            SERVICE_SLUG, MarkRequest(task_key=FIRST_TASK, to='failed', reason='no')
        )

        with pytest.raises(TransitionError):
            started_harness.service.prepare_verification(SERVICE_SLUG, create_verdict())

    @verdict_cases()
    def test_prepare_refuses_a_failed_or_blocked_verdict_without_a_reason(
        self, started_harness: ServiceHarness, verdict: VerifyVerdict
    ) -> None:
        with pytest.raises(VerdictReasonError):
            started_harness.service.prepare_verification(SERVICE_SLUG, create_verdict(verdict))

    def test_prepare_refuses_a_verified_verdict_with_a_reason(
        self, started_harness: ServiceHarness
    ) -> None:
        with pytest.raises(VerdictReasonRefusedError):
            started_harness.service.prepare_verification(
                SERVICE_SLUG, create_verdict('verified', 'why')
            )

    def test_prepare_refuses_a_closed_ticket(self, started_harness: ServiceHarness) -> None:
        started_harness.tickets.seed_status(SERVICE_SLUG, 'closed')

        with pytest.raises(ClosedTicketError):
            started_harness.service.prepare_verification(SERVICE_SLUG, create_verdict())


class TestVerify:
    def test_verify_marks_a_started_task_verified_with_the_commit(
        self, started_harness: ServiceHarness
    ) -> None:
        record = verify_as_asked(started_harness, OWNED_CHANGE)

        assert (record.status, record.commit, record.reasons) == ('verified', DONE_COMMIT, ())

    @pytest.fixture
    def off_head_request(self, started_harness: ServiceHarness) -> VerifyRequest:
        seen = started_harness.service.prepare_verification(SERVICE_SLUG, create_verdict())
        facts = replace(
            create_git_facts(changed_files=frozenset({OWNED_FILE, OUTSIDE_FILE})),
            head='fff9999',
            base_is_ancestor=False,
        )
        return VerifyRequest(
            seen=seen, commit=DONE_COMMIT, verdict='verified', reason=None, git=facts
        )

    def test_verify_records_a_verified_task_that_is_not_head_and_touched_other_files(
        self, started_harness: ServiceHarness, off_head_request: VerifyRequest
    ) -> None:
        record = started_harness.service.verify(SERVICE_SLUG, off_head_request)

        assert (record.status, record.commit, record.reasons) == ('verified', DONE_COMMIT, ())

    @verdict_cases()
    def test_verify_records_the_verdict_with_its_reason(
        self, started_harness: ServiceHarness, verdict: VerifyVerdict
    ) -> None:
        seen = started_harness.service.prepare_verification(
            SERVICE_SLUG, create_verdict(verdict, 'the test fails')
        )
        request = create_verify_request(
            seen, changed_files=OWNED_CHANGE, verdict=verdict, reason='the test fails'
        )

        record = started_harness.service.verify(SERVICE_SLUG, request)

        assert (record.status, record.commit, record.reasons) == (
            verdict,
            DONE_COMMIT,
            ('the test fails',),
        )

    @verdict_cases()
    def test_verify_refuses_a_failed_or_blocked_verdict_without_a_reason(
        self, started_harness: ServiceHarness, verdict: VerifyVerdict
    ) -> None:
        seen = started_harness.service.prepare_verification(
            SERVICE_SLUG, create_verdict(verdict, 'the test fails')
        )
        request = create_verify_request(
            seen, changed_files=OWNED_CHANGE, verdict=verdict, reason=None
        )

        with pytest.raises(VerdictReasonError):
            started_harness.service.verify(SERVICE_SLUG, request)

    def test_verify_refuses_a_verified_verdict_with_a_reason(
        self, started_harness: ServiceHarness
    ) -> None:
        seen = started_harness.service.prepare_verification(SERVICE_SLUG, create_verdict())
        request = create_verify_request(seen, changed_files=OWNED_CHANGE, reason='why')

        with pytest.raises(VerdictReasonRefusedError):
            started_harness.service.verify(SERVICE_SLUG, request)

    def move_task(self, harness: ServiceHarness, seen: TaskRecord, movement: Movement) -> None:
        address = (harness.ticket_id, FIRST_TASK)
        harness.task_ledger.held[address] = replace(
            seen, status=movement.status, base=movement.base, owned=movement.owned
        )

    @verify_movement_cases()
    def test_verify_refuses_a_task_that_moved_while_git_was_asked(
        self, started_harness: ServiceHarness, movement: Movement
    ) -> None:
        seen = started_harness.service.prepare_verification(SERVICE_SLUG, create_verdict())
        request = create_verify_request(seen, changed_files=OWNED_CHANGE)
        self.move_task(started_harness, seen, movement)

        with pytest.raises(TaskMovedError) as refused:
            started_harness.service.verify(SERVICE_SLUG, request)

        assert refused.value.changed == (movement.moved,)
        assert started_harness.held(FIRST_TASK).status == movement.status

    def test_verify_refuses_a_ticket_closed_while_git_was_asked(
        self, started_harness: ServiceHarness
    ) -> None:
        seen = started_harness.service.prepare_verification(SERVICE_SLUG, create_verdict())
        request = create_verify_request(seen, changed_files=OWNED_CHANGE)
        started_harness.tickets.seed_status(SERVICE_SLUG, 'closed')

        with pytest.raises(ClosedTicketError):
            started_harness.service.verify(SERVICE_SLUG, request)
