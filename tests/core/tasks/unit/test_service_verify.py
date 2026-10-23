from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.tasks import MarkRequest, TaskMovedError, TransitionError
from mightymodels_core.tickets import ClosedTicketError

from tests.core.tasks.service_builders import (
    BASE_COMMIT,
    COMMAND_KEY,
    DONE_COMMIT,
    FIRST_TASK,
    OWNED_FILE,
    SERVICE_SLUG,
    create_verify_request,
    verify_as_asked,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks import TaskRecord

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


class TestPrepareVerification:
    def test_prepare_returns_the_task_git_is_asked_about(
        self, started_harness: ServiceHarness
    ) -> None:
        task = started_harness.service.prepare_verification(SERVICE_SLUG, FIRST_TASK)

        assert (task.base, task.owned) == (BASE_COMMIT, (OWNED_FILE,))

    def test_prepare_refuses_a_task_that_was_never_started(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(TransitionError):
            service_harness.service.prepare_verification(SERVICE_SLUG, FIRST_TASK)

    def test_prepare_refuses_a_task_that_cannot_move_to_verified(
        self, started_harness: ServiceHarness
    ) -> None:
        started_harness.service.mark(
            SERVICE_SLUG, MarkRequest(task_key=FIRST_TASK, to='failed', reason='no')
        )

        with pytest.raises(TransitionError):
            started_harness.service.prepare_verification(SERVICE_SLUG, FIRST_TASK)

    def test_prepare_refuses_a_closed_ticket(self, started_harness: ServiceHarness) -> None:
        started_harness.tickets.seed_status(SERVICE_SLUG, 'closed')

        with pytest.raises(ClosedTicketError):
            started_harness.service.prepare_verification(SERVICE_SLUG, FIRST_TASK)


class TestVerify:
    def test_verify_marks_a_proven_task_verified_with_the_commit(
        self, proven_harness: ServiceHarness
    ) -> None:
        record = verify_as_asked(proven_harness, OWNED_CHANGE)

        assert (record.status, record.commit, record.reasons) == ('verified', DONE_COMMIT, ())

    def test_verify_blocks_a_task_with_no_receipt_and_lists_why(
        self, contracted_harness: ServiceHarness
    ) -> None:
        record = verify_as_asked(contracted_harness, OWNED_CHANGE)

        assert record.status == 'blocked'
        assert record.reasons == (f'{COMMAND_KEY} has no receipt at the current HEAD',)

    def test_verify_blocks_a_commit_that_touched_files_outside_the_owned_set(
        self, proven_harness: ServiceHarness
    ) -> None:
        record = verify_as_asked(proven_harness, frozenset({OWNED_FILE, OUTSIDE_FILE}))

        assert record.status == 'blocked'
        assert record.reasons == (f'changed outside the owned set: {OUTSIDE_FILE}',)

    def test_verify_counts_only_the_commands_of_its_own_task(
        self, foreign_command_harness: ServiceHarness
    ) -> None:
        record = verify_as_asked(foreign_command_harness, OWNED_CHANGE)

        assert record.status == 'verified'

    def move_task(self, harness: ServiceHarness, seen: TaskRecord, movement: Movement) -> None:
        address = (harness.ticket_id, FIRST_TASK)
        harness.task_ledger.held[address] = replace(
            seen, status=movement.status, base=movement.base, owned=movement.owned
        )

    @verify_movement_cases()
    def test_verify_refuses_a_task_that_moved_while_git_was_asked(
        self, proven_harness: ServiceHarness, movement: Movement
    ) -> None:
        seen = proven_harness.service.prepare_verification(SERVICE_SLUG, FIRST_TASK)
        request = create_verify_request(seen, changed_files=OWNED_CHANGE)
        self.move_task(proven_harness, seen, movement)

        with pytest.raises(TaskMovedError) as refused:
            proven_harness.service.verify(SERVICE_SLUG, request)

        assert refused.value.changed == (movement.moved,)
        assert proven_harness.held(FIRST_TASK).status == movement.status

    def test_verify_refuses_a_ticket_closed_while_git_was_asked(
        self, proven_harness: ServiceHarness
    ) -> None:
        seen = proven_harness.service.prepare_verification(SERVICE_SLUG, FIRST_TASK)
        request = create_verify_request(seen, changed_files=OWNED_CHANGE)
        proven_harness.tickets.seed_status(SERVICE_SLUG, 'closed')

        with pytest.raises(ClosedTicketError):
            proven_harness.service.verify(SERVICE_SLUG, request)
