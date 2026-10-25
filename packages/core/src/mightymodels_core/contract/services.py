"""The contract service: approves commands, reports their status, picks a run and records it.

It takes values and returns values. The caller passes HEAD in and renders the results this
service returns; the service never touches git, a process or the filesystem. Running the picked
commands stays with the caller, which asks `pick` before it runs and calls `record` after.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.contract.policy import (
    ApprovalPolicy,
    ContractOptions,
    PickPolicy,
    ReceiptAssessment,
)
from mightymodels_core.contract.records import Approval

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.contract.records import ApprovedCommand, Receipt, RecordedCommand
    from mightymodels_core.contract.repository import ContractRepository
    from mightymodels_core.primitives import Clock, Slug
    from mightymodels_core.tickets.repository import TicketRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class ApprovalResult:
    held: int
    new_keys: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class CommandStatus:
    command: RecordedCommand
    assessment: ReceiptAssessment


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractStatus:
    head: str | None
    commands: list[CommandStatus]

    @property
    def is_passing(self) -> bool:
        return all(status.assessment.is_passing for status in self.commands)


@dataclass(slots=True, kw_only=True, frozen=True)
class ContractService:
    tickets: TicketRepository
    contracts: ContractRepository
    clock: Clock
    options: ContractOptions = field(default_factory=ContractOptions)

    def approve(
        self, slug: Slug, commands: Sequence[ApprovedCommand], head: str | None
    ) -> ApprovalResult:
        ticket_id = self.tickets.staged_ticket(slug).id
        held = self.contracts.commands(ticket_id)
        policy = ApprovalPolicy(commands=commands, held=held, options=self.options)
        if problem := policy.get_approval_problem():
            raise problem

        new = policy.new_commands
        self.contracts.approve(ticket_id, new, Approval(at=self.clock.now(), head=head))
        return ApprovalResult(held=len(held) + len(new), new_keys=tuple(c.key for c in new))

    def status(self, slug: Slug, head: str | None) -> ContractStatus:
        ticket_id = self.tickets.staged_ticket(slug).id
        receipts = self.contracts.latest_receipts(ticket_id)
        statuses = [
            CommandStatus(
                command=command,
                assessment=ReceiptAssessment(receipt=receipts.get(command.key), head=head),
            )
            for command in self.contracts.commands(ticket_id)
        ]
        return ContractStatus(head=head, commands=statuses)

    def pick(self, slug: Slug, asked: Sequence[str] | None) -> list[RecordedCommand]:
        ticket_id = self.tickets.staged_ticket(slug).id
        held = self.contracts.commands(ticket_id)
        policy = PickPolicy(slug=slug, held=held, asked=asked)
        if problem := policy.get_pick_problem():
            raise problem

        return policy.picked_commands

    def record(self, slug: Slug, receipts: Sequence[Receipt]) -> None:
        ticket_id = self.tickets.staged_ticket(slug).id
        self.contracts.record(ticket_id, receipts)
