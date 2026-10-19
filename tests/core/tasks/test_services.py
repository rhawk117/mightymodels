from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.primitives import RedactedTextTooLongError, Slug
from mightymodels_core.tasks import (
    ArchitectSpentError,
    FixesSpentError,
    FixNotUnderwayError,
    InternSpentError,
    MarkRequest,
    ModeNeedsArchitectError,
    TaskMovedError,
    TaskOptions,
    TaskTooLargeError,
    TransitionError,
)
from mightymodels_core.tickets import ClosedTicketError, NotStagedError

from .conftest import (
    BASE_COMMIT,
    COMMAND_KEY,
    DONE_COMMIT,
    FIRST_TASK,
    OWNED_FILE,
    SECOND_TASK,
    SERVICE_SLUG,
    create_start_request,
    create_verify_request,
    verify_as_asked,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.schemas.tasks import TaskStatus
    from mightymodels_core.tasks import StartRequest, TaskRecord

    from .conftest import ServiceHarness

OTHER_SLUG = Slug('unstaged-subject')
SECRET = 'ghp_' + 'a' * 36
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


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedStart:
    name: str
    request: StartRequest
    error_type: type[Exception]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def verify_movement_cases() -> pytest.MarkDecorator:
    status = Movement(name='status', moved='status', status='blocked')
    base = Movement(name='base', moved='base', base='other01')
    owned = Movement(name='owned-set', moved='owned set', owned=(OWNED_FILE, 'src/b.py'))
    return pytest.mark.parametrize('movement', [status.param, base.param, owned.param])


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
        service_harness.tickets.mark_closed(SERVICE_SLUG)

        with pytest.raises(ClosedTicketError):
            service_harness.service.start(SERVICE_SLUG, create_start_request())


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
        started_harness.tickets.mark_closed(SERVICE_SLUG)

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
        proven_harness.tickets.mark_closed(SERVICE_SLUG)

        with pytest.raises(ClosedTicketError):
            proven_harness.service.verify(SERVICE_SLUG, request)


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
        started_harness.tickets.mark_closed(SERVICE_SLUG)
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
        started_harness.tickets.mark_closed(SERVICE_SLUG)

        with pytest.raises(ClosedTicketError):
            started_harness.service.record_failed_fix(SERVICE_SLUG, FIRST_TASK, 'a guess')


class TestShow:
    def test_show_lists_the_tasks_and_who_attempted_them(
        self, started_harness: ServiceHarness
    ) -> None:
        listing = started_harness.service.show(SERVICE_SLUG)

        assert [record.key for record in listing.records] == [FIRST_TASK]
        assert listing.attempts == {FIRST_TASK: {'engineer': 1}}

    def test_show_lists_nothing_for_a_ticket_with_no_task(
        self, service_harness: ServiceHarness
    ) -> None:
        listing = service_harness.service.show(SERVICE_SLUG)

        assert (listing.records, listing.attempts) == ([], {})

    def test_show_works_on_a_closed_ticket(self, started_harness: ServiceHarness) -> None:
        started_harness.tickets.mark_closed(SERVICE_SLUG)

        assert started_harness.service.show(SERVICE_SLUG).records

    def test_show_refuses_a_ticket_that_was_never_staged(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(NotStagedError):
            service_harness.service.show(OTHER_SLUG)


class TestReady:
    def test_ready_names_the_missing_plan_task_when_none_started(
        self, service_harness: ServiceHarness
    ) -> None:
        readiness = service_harness.service.ready(SERVICE_SLUG, DONE_COMMIT)

        assert readiness.problems == ['no plan task has been started']

    def test_ready_is_clear_when_every_plan_task_is_proven_at_head(
        self, verified_harness: ServiceHarness
    ) -> None:
        readiness = verified_harness.service.ready(SERVICE_SLUG, DONE_COMMIT)

        assert readiness.problems == []

    def test_ready_names_a_task_still_in_progress(self, proven_harness: ServiceHarness) -> None:
        readiness = proven_harness.service.ready(SERVICE_SLUG, DONE_COMMIT)

        assert readiness.problems == [f'{FIRST_TASK} is in-progress, not verified']

    def test_ready_names_a_command_with_no_receipt_at_head(
        self, verified_harness: ServiceHarness
    ) -> None:
        readiness = verified_harness.service.ready(SERVICE_SLUG, 'newer01')

        assert readiness.problems == [f'{COMMAND_KEY} has no receipt at the current HEAD']

    def test_ready_skips_the_commands_of_a_superseded_task(
        self, contracted_harness: ServiceHarness
    ) -> None:
        contracted_harness.service.mark(
            SERVICE_SLUG, MarkRequest(task_key=FIRST_TASK, to='superseded', reason='dropped')
        )

        readiness = contracted_harness.service.ready(SERVICE_SLUG, DONE_COMMIT)

        assert not any(COMMAND_KEY in problem for problem in readiness.problems)

    def test_ready_refuses_a_ticket_that_was_never_staged(
        self, service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(NotStagedError):
            service_harness.service.ready(OTHER_SLUG, DONE_COMMIT)
