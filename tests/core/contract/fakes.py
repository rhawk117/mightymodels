"""The contract repository kept in memory."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.contract.records import (
    COMMANDS,
    RecordedCommand,
    duplicate_command_error,
    owning_task,
    unapproved_command_error,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.contract.records import Approval, ApprovedCommand, Receipt

type CommandAddress = tuple[int, str]


@dataclass(slots=True, kw_only=True, frozen=True)
class PlacedCommand:
    command: RecordedCommand
    approved_by: str
    approval: Approval


@dataclass(slots=True, kw_only=True, frozen=True)
class PlacedReceipt:
    ticket_id: int
    receipt: Receipt


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractLedger:
    approved: dict[CommandAddress, PlacedCommand] = field(default_factory=dict)
    receipts: list[PlacedReceipt] = field(default_factory=list)

    def keys_of(self, ticket_id: int) -> list[str]:
        return [key for owner, key in self.approved if owner == ticket_id]


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeContractRepository:
    ledger: ContractLedger

    def commands(self, ticket_id: int) -> list[RecordedCommand]:
        held = [
            placed.command
            for (owner, _), placed in self.ledger.approved.items()
            if owner == ticket_id
        ]
        if (error := COMMANDS.error(held, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return sorted(held, key=lambda command: command.key)

    def latest_receipts(self, ticket_id: int) -> dict[str, Receipt]:
        latest = {
            placed.receipt.key: placed.receipt
            for placed in self.ledger.receipts
            if placed.ticket_id == ticket_id
        }
        if (error := COMMANDS.error(latest, owner=f'ticket {ticket_id}')) is not None:
            raise error
        return latest

    def approve(
        self, ticket_id: int, commands: Sequence[ApprovedCommand], approval: Approval
    ) -> None:
        held_keys = self.ledger.keys_of(ticket_id)
        if (duplicate := duplicate_command_error(ticket_id, held_keys, commands)) is not None:
            raise duplicate

        total = len(held_keys) + len(commands)
        if (error := COMMANDS.write_error(total, owner=f'ticket {ticket_id}')) is not None:
            raise error

        for command in commands:
            recorded = RecordedCommand(
                key=command.key,
                task_key=owning_task(command.key),
                argv=command.argv,
                expect_exit=command.expect_exit,
                timeout=command.timeout,
            )
            self.ledger.approved[ticket_id, command.key] = PlacedCommand(
                command=recorded, approved_by=command.approved_by, approval=approval
            )

    def record(self, ticket_id: int, receipts: Sequence[Receipt]) -> None:
        approved_keys = self.ledger.keys_of(ticket_id)
        if (unapproved := unapproved_command_error(ticket_id, approved_keys, receipts)) is not None:
            raise unapproved

        self.ledger.receipts.extend(
            PlacedReceipt(ticket_id=ticket_id, receipt=receipt) for receipt in receipts
        )
