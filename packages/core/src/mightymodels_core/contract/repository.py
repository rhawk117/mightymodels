"""The seam under the contract services: the approved commands of one ticket and their receipts.

`commands` and `latest_receipts` refuse to answer from part of the rows. `approve` stores every
command it is given or none: it refuses a key the ticket already holds, or one twice in the
batch, with `DuplicateCommandError`, and a batch that leaves the ticket with more commands than one
read returns with `WriteLimitError`. `record` stores every receipt or none, and refuses a receipt
for a key the ticket has not approved with `UnapprovedCommandError`.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.contract.records import (
        Approval,
        ApprovedCommand,
        Receipt,
        RecordedCommand,
    )


@runtime_checkable
class ContractRepository(Protocol):
    def commands(self, ticket_id: int) -> list[RecordedCommand]: ...

    def latest_receipts(self, ticket_id: int) -> dict[str, Receipt]: ...

    def approve(
        self, ticket_id: int, commands: Sequence[ApprovedCommand], approval: Approval
    ) -> None: ...

    def record(self, ticket_id: int, receipts: Sequence[Receipt]) -> None: ...
