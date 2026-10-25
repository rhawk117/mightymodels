"""The contract service over the fake repositories: approve, status, pick and record."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import (
    Approval,
    ChangedCommandError,
    InvalidArgvError,
    InvalidTimeoutError,
    MissingApprovalError,
    NoContractError,
    UnapprovedCommandError,
    UnknownCommandError,
)
from mightymodels_core.primitives import Slug
from mightymodels_core.tickets import NotStagedError

from tests.core.contract.contract_builders import (
    FIRST_KEY,
    HEAD,
    SECOND_KEY,
    SERVICE_MOMENT,
    SERVICE_SLUG,
    create_command,
    create_receipt,
)

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.contract import ApprovedCommand

    from tests.core.contract.contract_builders import ServiceHarness

UNSTAGED_SLUG = Slug('unstaged-subject')
OLD_HEAD = 'old0001'


@dataclass(slots=True, kw_only=True, frozen=True)
class RefusedApproval:
    name: str
    command: ApprovedCommand
    error_type: type[Exception]

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def approval_refusal_cases() -> pytest.MarkDecorator:
    changed = RefusedApproval(
        name='changed-argv',
        command=create_command(FIRST_KEY, argv=('make', 'lint')),
        error_type=ChangedCommandError,
    )
    shell_string = RefusedApproval(
        name='empty-argv', command=create_command(SECOND_KEY, argv=()), error_type=InvalidArgvError
    )
    slow = RefusedApproval(
        name='timeout-over-limit',
        command=replace(create_command(SECOND_KEY), timeout=3601),
        error_type=InvalidTimeoutError,
    )
    unsigned = RefusedApproval(
        name='blank-approver',
        command=replace(create_command(SECOND_KEY), approved_by=' '),
        error_type=MissingApprovalError,
    )
    cases = [changed.param, shell_string.param, slow.param, unsigned.param]
    return pytest.mark.parametrize('refused', cases)


class TestApprove:
    def test_new_commands_are_written_with_head_and_clock_time(
        self, service_harness: ServiceHarness
    ) -> None:
        result = service_harness.service.approve(SERVICE_SLUG, [create_command(FIRST_KEY)], HEAD)

        placed = service_harness.ledger.approved[service_harness.ticket_id, FIRST_KEY]
        assert placed.approval == Approval(at=SERVICE_MOMENT, head=HEAD)
        assert (result.held, result.new_keys) == (1, (FIRST_KEY,))

    def test_identical_reapproval_writes_nothing(
        self, stocked_service_harness: ServiceHarness
    ) -> None:
        harness = stocked_service_harness
        again = [create_command(FIRST_KEY), create_command('T1.AC-3')]

        result = harness.service.approve(SERVICE_SLUG, again, HEAD)

        assert (result.held, result.new_keys) == (3, ('T1.AC-3',))
        assert len(harness.ledger.approved) == 3

    @approval_refusal_cases()
    def test_refused_approval_writes_nothing(
        self, stocked_service_harness: ServiceHarness, refused: RefusedApproval
    ) -> None:
        harness = stocked_service_harness
        batch = [create_command('T1.AC-3'), refused.command]

        with pytest.raises(refused.error_type):
            harness.service.approve(SERVICE_SLUG, batch, HEAD)

        assert len(harness.ledger.approved) == 2

    def test_unstaged_ticket_is_refused(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(NotStagedError):
            service_harness.service.approve(UNSTAGED_SLUG, [create_command(FIRST_KEY)], HEAD)


class TestStatus:
    def test_a_command_with_no_receipt_is_never_run(
        self, stocked_service_harness: ServiceHarness
    ) -> None:
        status = stocked_service_harness.service.status(SERVICE_SLUG, HEAD)

        assert [entry.assessment.state for entry in status.commands] == ['never-run', 'never-run']
        assert not status.is_passing

    def test_a_receipt_from_another_head_is_stale(
        self, stocked_service_harness: ServiceHarness
    ) -> None:
        harness = stocked_service_harness
        old = replace(create_receipt(FIRST_KEY), head=OLD_HEAD)
        harness.service.record(SERVICE_SLUG, [old])

        status = harness.service.status(SERVICE_SLUG, HEAD)

        assert status.commands[0].assessment.state == 'stale'
        assert not status.is_passing

    def test_every_command_passing_at_head_passes(
        self, stocked_service_harness: ServiceHarness
    ) -> None:
        harness = stocked_service_harness
        harness.service.record(
            SERVICE_SLUG, [create_receipt(FIRST_KEY), create_receipt(SECOND_KEY)]
        )

        status = harness.service.status(SERVICE_SLUG, HEAD)

        assert status.is_passing
        assert status.head == HEAD

    def test_a_failure_at_head_does_not_pass(self, stocked_service_harness: ServiceHarness) -> None:
        harness = stocked_service_harness
        harness.service.record(
            SERVICE_SLUG, [create_receipt(FIRST_KEY), create_receipt(SECOND_KEY, 'fail')]
        )

        assert not harness.service.status(SERVICE_SLUG, HEAD).is_passing

    def test_no_head_is_never_passing(self, stocked_service_harness: ServiceHarness) -> None:
        harness = stocked_service_harness
        harness.service.record(
            SERVICE_SLUG, [create_receipt(FIRST_KEY), create_receipt(SECOND_KEY)]
        )

        assert not harness.service.status(SERVICE_SLUG, None).is_passing


class TestPick:
    def test_no_ids_picks_the_whole_contract(self, stocked_service_harness: ServiceHarness) -> None:
        picked = stocked_service_harness.service.pick(SERVICE_SLUG, None)

        assert [command.key for command in picked] == [FIRST_KEY, SECOND_KEY]

    def test_asked_ids_pick_those_commands(self, stocked_service_harness: ServiceHarness) -> None:
        picked = stocked_service_harness.service.pick(SERVICE_SLUG, [SECOND_KEY])

        assert [command.key for command in picked] == [SECOND_KEY]

    def test_a_ticket_with_no_contract_is_refused(self, service_harness: ServiceHarness) -> None:
        with pytest.raises(NoContractError):
            service_harness.service.pick(SERVICE_SLUG, None)

    def test_an_unknown_id_is_refused(self, stocked_service_harness: ServiceHarness) -> None:
        with pytest.raises(UnknownCommandError):
            stocked_service_harness.service.pick(SERVICE_SLUG, [FIRST_KEY, 'T9.AC-9'])


class TestRecord:
    def test_receipts_are_stored_against_the_ticket(
        self, stocked_service_harness: ServiceHarness
    ) -> None:
        harness = stocked_service_harness

        harness.service.record(SERVICE_SLUG, [create_receipt(FIRST_KEY)])

        latest = harness.contracts.latest_receipts(harness.ticket_id)
        assert latest == {FIRST_KEY: create_receipt(FIRST_KEY)}

    def test_a_receipt_for_an_unapproved_command_is_refused(
        self, stocked_service_harness: ServiceHarness
    ) -> None:
        with pytest.raises(UnapprovedCommandError):
            stocked_service_harness.service.record(SERVICE_SLUG, [create_receipt('T9.AC-9')])
