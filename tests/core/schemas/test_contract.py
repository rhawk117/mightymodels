from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.database import DuplicateRowError, MissingParentError
from mightymodels_core.schemas.contract import (
    APPROVE_CONTRACT_COMMAND,
    CONTRACT_COMMAND_COUNT,
    CONTRACT_COMMANDS_OF_TICKET,
    LATEST_RECEIPTS,
    RECORD_RECEIPT,
    ApproveContractCommandParams,
    ContractCommandCountParams,
    ContractCommandsParams,
    RecordReceiptParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database
    from mightymodels_core.schemas.contract import Outcome

pytestmark = pytest.mark.integration

APPROVED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
RAN_AT = datetime(2026, 1, 2, 4, 0, 0, tzinfo=UTC)


def command(ticket_id: int, key: str, task_key: str | None = None) -> ApproveContractCommandParams:
    return ApproveContractCommandParams(
        ticket_id=ticket_id,
        command_key=key,
        task_key=task_key,
        argv=['uv', 'run', 'pytest', '-q'],
        expect_exit=0,
        timeout=300,
        approved_by='owner',
        approved_at=APPROVED_AT,
        head=None,
    )


def receipt(command_id: int, outcome: Outcome, stdout_tail: str) -> RecordReceiptParams:
    return RecordReceiptParams(
        contract_command_id=command_id,
        argv=['uv', 'run', 'pytest', '-q'],
        outcome=outcome,
        exit=None if outcome == 'timeout' else 0,
        duration_ms=120,
        stdout_tail=stdout_tail,
        stderr_tail='',
        digest='sha256:abc',
        head='abc123',
        phase='task',
        at=RAN_AT,
    )


class TestCommands:
    def test_a_batch_of_commands_is_approved_and_read_back_in_key_order(
        self, database: Database, ticket_id: int
    ) -> None:
        batch = [command(ticket_id, 'T1.AC-2', 'T1'), command(ticket_id, 'I1')]
        with database.write() as unit:
            approved = unit.run_many(APPROVE_CONTRACT_COMMAND, batch)

        with database.read() as unit:
            commands = unit.all(
                CONTRACT_COMMANDS_OF_TICKET, ContractCommandsParams(ticket_id=ticket_id, limit=10)
            )
            count = unit.one(
                CONTRACT_COMMAND_COUNT, ContractCommandCountParams(ticket_id=ticket_id)
            )

        assert approved == 2
        assert [row.command_key for row in commands] == ['I1', 'T1.AC-2']
        assert commands[1].task_key == 'T1'
        assert commands[0].task_key is None
        assert commands[0].argv == ['uv', 'run', 'pytest', '-q']
        assert commands[0].expect_exit == 0
        assert commands[0].timeout == 300
        assert commands[0].approved_by == 'owner'
        assert commands[0].approved_at == APPROVED_AT
        assert commands[0].head is None
        assert count is not None
        assert count.count == 2

    def test_a_command_key_is_unique_within_a_ticket(
        self, database: Database, ticket_id: int
    ) -> None:
        with database.write() as unit:
            unit.run_many(APPROVE_CONTRACT_COMMAND, [command(ticket_id, 'I1')])

        with pytest.raises(DuplicateRowError), database.write() as unit:
            unit.run_many(APPROVE_CONTRACT_COMMAND, [command(ticket_id, 'I1')])

    def test_a_command_needs_a_ticket(self, database: Database) -> None:
        with pytest.raises(MissingParentError), database.write() as unit:
            unit.run_many(APPROVE_CONTRACT_COMMAND, [command(999, 'I1')])


class TestReceipts:
    @pytest.fixture
    def command_ids(self, database: Database, ticket_id: int) -> dict[str, int]:
        with database.write() as unit:
            unit.run_many(
                APPROVE_CONTRACT_COMMAND, [command(ticket_id, 'I1'), command(ticket_id, 'I2')]
            )
        with database.read() as unit:
            commands = unit.all(
                CONTRACT_COMMANDS_OF_TICKET, ContractCommandsParams(ticket_id=ticket_id, limit=10)
            )
        return {row.command_key: row.id for row in commands}

    def test_the_latest_receipt_of_each_command_is_read_back(
        self, database: Database, ticket_id: int, command_ids: dict[str, int]
    ) -> None:
        batch = [
            receipt(command_ids['I1'], 'fail', 'first run'),
            receipt(command_ids['I2'], 'timeout', 'only run'),
            receipt(command_ids['I1'], 'pass', 'second run'),
        ]
        with database.write() as unit:
            recorded = unit.run_many(RECORD_RECEIPT, batch)

        with database.read() as unit:
            latest = unit.all(
                LATEST_RECEIPTS, ContractCommandsParams(ticket_id=ticket_id, limit=10)
            )

        by_key = {row.command_key: row for row in latest}
        assert recorded == 3
        assert set(by_key) == {'I1', 'I2'}
        assert by_key['I1'].outcome == 'pass'
        assert by_key['I1'].stdout_tail == 'second run'
        assert by_key['I1'].argv == ['uv', 'run', 'pytest', '-q']
        assert by_key['I1'].exit == 0
        assert by_key['I1'].duration_ms == 120
        assert by_key['I1'].digest == 'sha256:abc'
        assert by_key['I1'].head == 'abc123'
        assert by_key['I1'].phase == 'task'
        assert by_key['I1'].at == RAN_AT
        assert by_key['I2'].outcome == 'timeout'
        assert by_key['I2'].exit is None

    def test_a_command_without_receipts_has_no_latest_receipt(
        self, database: Database, ticket_id: int, command_ids: dict[str, int]
    ) -> None:
        with database.write() as unit:
            unit.run_many(RECORD_RECEIPT, [receipt(command_ids['I1'], 'pass', 'ran')])

        with database.read() as unit:
            latest = unit.all(
                LATEST_RECEIPTS, ContractCommandsParams(ticket_id=ticket_id, limit=10)
            )

        assert [row.command_key for row in latest] == ['I1']

    def test_a_receipt_needs_its_command(self, database: Database) -> None:
        with pytest.raises(MissingParentError), database.write() as unit:
            unit.run_many(RECORD_RECEIPT, [receipt(999, 'pass', 'ran')])
