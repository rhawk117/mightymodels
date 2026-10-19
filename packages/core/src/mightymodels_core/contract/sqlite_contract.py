"""The contract repository over a core unit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.contract.records import (
    COMMANDS,
    Receipt,
    RecordedCommand,
    duplicate_command_error,
    owning_task,
    unapproved_command_error,
)
from mightymodels_core.primitives import redact
from mightymodels_core.schemas.contract import (
    APPROVE_CONTRACT_COMMAND,
    CONTRACT_COMMANDS_OF_TICKET,
    LATEST_RECEIPTS,
    RECORD_RECEIPT,
    ApproveContractCommandParams,
    ContractCommandsParams,
    RecordReceiptParams,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.contract.records import Approval, ApprovedCommand
    from mightymodels_core.database import Unit
    from mightymodels_core.schemas.contract import ContractCommandRow, ReceiptRow


def command_of(row: ContractCommandRow) -> RecordedCommand:
    return RecordedCommand(
        key=row.command_key,
        task_key=owning_task(row.command_key),
        argv=tuple(row.argv),
        expect_exit=row.expect_exit,
        timeout=row.timeout,
    )


def receipt_of(row: ReceiptRow) -> Receipt:
    return Receipt(
        key=row.command_key,
        argv=tuple(row.argv),
        outcome=row.outcome,
        exit=row.exit,
        duration_ms=row.duration_ms,
        stdout_tail=redact(row.stdout_tail),
        stderr_tail=redact(row.stderr_tail),
        digest=row.digest,
        head=row.head,
        phase=row.phase,
        at=row.at,
    )


def approve_params_of(
    ticket_id: int, command: ApprovedCommand, approval: Approval
) -> ApproveContractCommandParams:
    return ApproveContractCommandParams(
        ticket_id=ticket_id,
        command_key=command.key,
        task_key=owning_task(command.key),
        argv=list(command.argv),
        expect_exit=command.expect_exit,
        timeout=command.timeout,
        approved_by=command.approved_by,
        approved_at=approval.at,
        head=approval.head,
    )


def receipt_params_of(command_id: int, receipt: Receipt) -> RecordReceiptParams:
    return RecordReceiptParams(
        contract_command_id=command_id,
        argv=list(receipt.argv),
        outcome=receipt.outcome,
        exit=receipt.exit,
        duration_ms=receipt.duration_ms,
        stdout_tail=receipt.stdout_tail,
        stderr_tail=receipt.stderr_tail,
        digest=receipt.digest,
        head=receipt.head,
        phase=receipt.phase,
        at=receipt.at,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteContractRepository:
    unit: Unit

    def commands(self, ticket_id: int) -> list[RecordedCommand]:
        rows = self.command_rows(ticket_id)
        return [command_of(row) for row in rows]

    def latest_receipts(self, ticket_id: int) -> dict[str, Receipt]:
        params = ContractCommandsParams(ticket_id=ticket_id, limit=COMMANDS.fetched)
        rows = self.unit.all(LATEST_RECEIPTS, params)
        if (error := COMMANDS.error(rows, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return {row.command_key: receipt_of(row) for row in rows}

    def approve(
        self, ticket_id: int, commands: Sequence[ApprovedCommand], approval: Approval
    ) -> None:
        held_keys = {row.command_key for row in self.command_rows(ticket_id)}
        if (duplicate := duplicate_command_error(ticket_id, held_keys, commands)) is not None:
            raise duplicate

        total = len(held_keys) + len(commands)
        if (error := COMMANDS.write_error(total, owner=f'ticket {ticket_id}')) is not None:
            raise error

        batch = [approve_params_of(ticket_id, command, approval) for command in commands]
        self.unit.run_many(APPROVE_CONTRACT_COMMAND, batch)

    def record(self, ticket_id: int, receipts: Sequence[Receipt]) -> None:
        ids = {row.command_key: row.id for row in self.command_rows(ticket_id)}
        if (unapproved := unapproved_command_error(ticket_id, ids.keys(), receipts)) is not None:
            raise unapproved

        batch = [receipt_params_of(ids[receipt.key], receipt) for receipt in receipts]
        self.unit.run_many(RECORD_RECEIPT, batch)

    def command_rows(self, ticket_id: int) -> list[ContractCommandRow]:
        params = ContractCommandsParams(ticket_id=ticket_id, limit=COMMANDS.fetched)
        rows = self.unit.all(CONTRACT_COMMANDS_OF_TICKET, params)
        if (error := COMMANDS.error(rows, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return rows
