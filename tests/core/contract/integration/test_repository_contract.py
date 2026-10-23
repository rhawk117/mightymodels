"""Every contract repository case runs against the sqlite store and the fake."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.contract import (
    ContractRepository,
    DuplicateCommandError,
    RecordedCommand,
    UnapprovedCommandError,
)
from mightymodels_core.contract.records import COMMANDS
from mightymodels_core.contract.tests.fakes import ContractLedger, FakeContractRepository
from mightymodels_core.primitives import TaskId, WriteLimitError

from tests.core.contract.conftest import APPROVAL, create_command, create_receipt

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet

    from tests.core.contract.conftest import ContractHarness


@dataclass(slots=True, kw_only=True, frozen=True)
class OwnerCase:
    key: str
    task_key: TaskId | None

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.key)


def command_owner_cases() -> pytest.MarkDecorator:
    cases = [
        OwnerCase(key='T7.AC-1', task_key=TaskId('T7')),
        OwnerCase(key='C2.ci', task_key=TaskId('C2')),
        OwnerCase(key='lint', task_key=None),
        OwnerCase(key='not a task.AC-1', task_key=None),
    ]
    return pytest.mark.parametrize('case', [case.param for case in cases])


class TestImplementations:
    def test_fake_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeContractRepository(ledger=ContractLedger()), ContractRepository)

    def test_repository_satisfies_the_protocol(self, harness: ContractHarness) -> None:
        assert isinstance(harness.contract, ContractRepository)


class TestApprove:
    @pytest.fixture
    def approved(self, harness: ContractHarness) -> ContractHarness:
        commands = [create_command('T2.AC-1'), create_command('T1.AC-1', argv=('make', 'lint'))]
        harness.contract.approve(harness.ticket_id, commands, APPROVAL)
        return harness

    def test_no_commands_are_held_before_an_approval(self, harness: ContractHarness) -> None:
        assert harness.contract.commands(harness.ticket_id) == []

    def test_approved_commands_are_read_back_ordered_by_key(
        self, approved: ContractHarness
    ) -> None:
        expected = [
            RecordedCommand(
                key='T1.AC-1',
                task_key=TaskId('T1'),
                argv=('make', 'lint'),
                expect_exit=0,
                timeout=300,
            ),
            RecordedCommand(
                key='T2.AC-1',
                task_key=TaskId('T2'),
                argv=('make', 'test'),
                expect_exit=0,
                timeout=300,
            ),
        ]

        assert approved.contract.commands(approved.ticket_id) == expected

    @command_owner_cases()
    def test_owning_task_comes_from_the_key(
        self, harness: ContractHarness, case: OwnerCase
    ) -> None:
        harness.contract.approve(harness.ticket_id, [create_command(case.key)], APPROVAL)

        (command,) = harness.contract.commands(harness.ticket_id)
        assert command.task_key == case.task_key

    def test_commands_of_another_ticket_are_not_read(self, approved: ContractHarness) -> None:
        assert approved.contract.commands(approved.other_ticket_id) == []

    def test_another_ticket_may_approve_the_same_key(self, approved: ContractHarness) -> None:
        approved.contract.approve(approved.other_ticket_id, [create_command('T1.AC-1')], APPROVAL)

        assert len(approved.contract.commands(approved.other_ticket_id)) == 1

    def test_key_the_ticket_holds_is_refused(self, approved: ContractHarness) -> None:
        with pytest.raises(DuplicateCommandError):
            approved.contract.approve(approved.ticket_id, [create_command('T1.AC-1')], APPROVAL)

    def test_refused_batch_stores_none_of_it(self, approved: ContractHarness) -> None:
        batch = [create_command('T3.AC-1'), create_command('T1.AC-1')]

        with pytest.raises(DuplicateCommandError):
            approved.contract.approve(approved.ticket_id, batch, APPROVAL)

        keys = [command.key for command in approved.contract.commands(approved.ticket_id)]
        assert keys == ['T1.AC-1', 'T2.AC-1']

    def test_key_twice_in_one_batch_is_refused(self, harness: ContractHarness) -> None:
        batch = [create_command('T1.AC-1'), create_command('T1.AC-1')]

        with pytest.raises(DuplicateCommandError):
            harness.contract.approve(harness.ticket_id, batch, APPROVAL)

        assert harness.contract.commands(harness.ticket_id) == []


class TestRecord:
    @pytest.fixture
    def approved(self, harness: ContractHarness) -> ContractHarness:
        commands = [create_command('T1.AC-1'), create_command('T2.AC-1')]
        harness.contract.approve(harness.ticket_id, commands, APPROVAL)
        return harness

    def test_no_receipts_are_held_before_a_run(self, approved: ContractHarness) -> None:
        assert approved.contract.latest_receipts(approved.ticket_id) == {}

    def test_receipt_is_read_back_as_recorded(self, approved: ContractHarness) -> None:
        receipt = create_receipt('T1.AC-1')

        approved.contract.record(approved.ticket_id, [receipt])

        assert approved.contract.latest_receipts(approved.ticket_id) == {'T1.AC-1': receipt}

    def test_latest_receipt_of_each_command_is_read(self, approved: ContractHarness) -> None:
        failed = create_receipt('T1.AC-1', 'fail', day=3)
        passed = create_receipt('T1.AC-1', 'pass', day=4)
        other = create_receipt('T2.AC-1', 'timeout', day=3)

        approved.contract.record(approved.ticket_id, [failed, other])
        approved.contract.record(approved.ticket_id, [passed])

        latest = approved.contract.latest_receipts(approved.ticket_id)
        assert latest == {'T1.AC-1': passed, 'T2.AC-1': other}

    def test_receipts_of_another_ticket_are_not_read(self, approved: ContractHarness) -> None:
        approved.contract.approve(approved.other_ticket_id, [create_command('T1.AC-1')], APPROVAL)
        approved.contract.record(approved.other_ticket_id, [create_receipt('T1.AC-1')])

        assert approved.contract.latest_receipts(approved.ticket_id) == {}

    def test_receipt_for_an_unapproved_key_is_refused(self, approved: ContractHarness) -> None:
        with pytest.raises(UnapprovedCommandError):
            approved.contract.record(approved.ticket_id, [create_receipt('T9.AC-1')])

    def test_receipt_for_a_key_only_another_ticket_approved_is_refused(
        self, approved: ContractHarness
    ) -> None:
        approved.contract.approve(approved.other_ticket_id, [create_command('T9.AC-1')], APPROVAL)

        with pytest.raises(UnapprovedCommandError):
            approved.contract.record(approved.ticket_id, [create_receipt('T9.AC-1')])

    def test_refused_batch_stores_none_of_it(self, approved: ContractHarness) -> None:
        batch = [create_receipt('T1.AC-1'), create_receipt('T9.AC-1')]

        with pytest.raises(UnapprovedCommandError):
            approved.contract.record(approved.ticket_id, batch)

        assert approved.contract.latest_receipts(approved.ticket_id) == {}


class TestCommandCap:
    held_commands = COMMANDS.rows

    @pytest.fixture
    def full_harness(self, harness: ContractHarness) -> ContractHarness:
        commands = [create_command(f'T{number}.AC-1') for number in range(self.held_commands)]
        harness.contract.approve(harness.ticket_id, commands, APPROVAL)
        return harness

    def test_approval_past_the_cap_is_refused(self, full_harness: ContractHarness) -> None:
        with pytest.raises(WriteLimitError):
            full_harness.contract.approve(
                full_harness.ticket_id, [create_command('T-over.AC-1')], APPROVAL
            )

    def test_refused_approval_stores_none_of_it(self, full_harness: ContractHarness) -> None:
        batch = [create_command('T-over.AC-1'), create_command('T-over.AC-2')]

        with pytest.raises(WriteLimitError):
            full_harness.contract.approve(full_harness.ticket_id, batch, APPROVAL)

        assert len(full_harness.contract.commands(full_harness.ticket_id)) == self.held_commands

    def test_commands_at_the_cap_are_read_back(self, full_harness: ContractHarness) -> None:
        assert len(full_harness.contract.commands(full_harness.ticket_id)) == self.held_commands

    def test_receipts_at_the_cap_are_read_back(self, full_harness: ContractHarness) -> None:
        receipts = [create_receipt(f'T{number}.AC-1') for number in range(self.held_commands)]

        full_harness.contract.record(full_harness.ticket_id, receipts)

        latest = full_harness.contract.latest_receipts(full_harness.ticket_id)
        assert len(latest) == self.held_commands
