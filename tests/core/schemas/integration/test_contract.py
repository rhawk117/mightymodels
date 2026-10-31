from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from mightymodels_core.database import DatabaseError, DuplicateRowError, MissingParentError
from mightymodels_core.schemas.contract import (
    APPROVE_CONTRACT_COMMAND,
    CONTRACT_COMMANDS_OF_TICKET,
    LATEST_RECEIPTS,
    RECORD_RECEIPT,
    RETIRE_CONTRACT_COMMAND,
    ApproveContractCommandParams,
    ContractCommandsParams,
    RecordReceiptParams,
    RetireContractCommandParams,
)

if TYPE_CHECKING:
    from mightymodels_core.database import Database
    from mightymodels_core.schemas.contract import ApprovalSource, Outcome

APPROVED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
RETIRED_AT = datetime(2026, 1, 3, 3, 4, 5, tzinfo=UTC)
RAN_AT = datetime(2026, 1, 2, 4, 0, 0, tzinfo=UTC)


def command(ticket_id: int, key: str, source: str = 'form') -> ApproveContractCommandParams:
    return ApproveContractCommandParams(
        ticket_id=ticket_id,
        command_key=key,
        argv=['uv', 'run', 'pytest', '-q'],
        expect_exit=0,
        timeout=300,
        approved_by='owner',
        approval_source=cast('ApprovalSource', source),
        approved_at=APPROVED_AT,
        head=None,
    )


def retirement(ticket_id: int, key: str, source: str = 'form') -> RetireContractCommandParams:
    return RetireContractCommandParams(
        ticket_id=ticket_id,
        command_key=key,
        retired_by='owner',
        retired_why='no longer applies',
        retired_approval_source=cast('ApprovalSource', source),
        retired_at=RETIRED_AT,
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
        batch = [command(ticket_id, 'I2'), command(ticket_id, 'I1')]
        with database.write() as unit:
            approved = unit.run_many(APPROVE_CONTRACT_COMMAND, batch)

        with database.read() as unit:
            commands = unit.all(
                CONTRACT_COMMANDS_OF_TICKET, ContractCommandsParams(ticket_id=ticket_id, limit=10)
            )

        assert approved == 2
        assert [row.command_key for row in commands] == ['I1', 'I2']
        assert commands[0].argv == ['uv', 'run', 'pytest', '-q']
        assert commands[0].expect_exit == 0
        assert commands[0].timeout == 300
        assert commands[0].approved_by == 'owner'
        assert commands[0].approval_source == 'form'
        assert commands[0].approved_at == APPROVED_AT
        assert commands[0].head is None

    def test_a_fallback_approval_reads_back_as_fallback(
        self, database: Database, ticket_id: int
    ) -> None:
        with database.write() as unit:
            unit.run_many(APPROVE_CONTRACT_COMMAND, [command(ticket_id, 'I1', 'fallback')])

        with database.read() as unit:
            (row,) = unit.all(
                CONTRACT_COMMANDS_OF_TICKET, ContractCommandsParams(ticket_id=ticket_id, limit=10)
            )

        assert row.approval_source == 'fallback'

    def test_an_unknown_approval_source_is_refused(
        self, database: Database, ticket_id: int
    ) -> None:
        unknown = command(ticket_id, 'I1', 'claimed')

        with pytest.raises(DatabaseError), database.write() as unit:
            unit.run_many(APPROVE_CONTRACT_COMMAND, [unknown])

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


class TestRetirement:
    def test_a_retirement_is_read_back_on_its_own_row(
        self, database: Database, ticket_id: int
    ) -> None:
        with database.write() as unit:
            unit.run_many(APPROVE_CONTRACT_COMMAND, [command(ticket_id, 'I1')])
            retired = unit.run(RETIRE_CONTRACT_COMMAND, retirement(ticket_id, 'I1'))

        with database.read() as unit:
            (row,) = unit.all(
                CONTRACT_COMMANDS_OF_TICKET, ContractCommandsParams(ticket_id=ticket_id, limit=10)
            )

        assert retired == 1
        assert row.retired_by == 'owner'
        assert row.retired_why == 'no longer applies'
        assert row.retired_approval_source == 'form'
        assert row.retired_at == RETIRED_AT

    def test_an_unretired_command_reads_back_without_retirement(
        self, database: Database, ticket_id: int
    ) -> None:
        with database.write() as unit:
            unit.run_many(APPROVE_CONTRACT_COMMAND, [command(ticket_id, 'I1')])

        with database.read() as unit:
            (row,) = unit.all(
                CONTRACT_COMMANDS_OF_TICKET, ContractCommandsParams(ticket_id=ticket_id, limit=10)
            )

        assert row.retired_at is None
        assert row.retired_by is None

    def test_an_unknown_retirement_source_is_refused(
        self, database: Database, ticket_id: int
    ) -> None:
        with database.write() as unit:
            unit.run_many(APPROVE_CONTRACT_COMMAND, [command(ticket_id, 'I1')])

        with pytest.raises(DatabaseError), database.write() as unit:
            unit.run(RETIRE_CONTRACT_COMMAND, retirement(ticket_id, 'I1', 'claimed'))


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
