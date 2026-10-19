"""The seam under the investigation services: investigations and their ledger entries.

`add_investigation` refuses a key the repository already holds with `DuplicateInvestigationError`.
`append` stores every entry or none: it refuses a key that was never added with
`InvestigationNotFoundError`, a seq the ledger already holds, or one twice in the batch, with
`DuplicateEntryError`, and a batch that leaves the ledger with more entries than one read returns
with `WriteLimitError`. `entries` refuses to answer from part of the rows. A key that was never
added has no entries and no investigation. `unrecorded` answers which of the keys it is given were
never added, with or without entries. `latest_rounds` lists the newest investigations that hold
entries.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from mightymodels_core.investigations.records import (
        InvestigationRecord,
        LatestRound,
        LedgerRecord,
    )
    from mightymodels_core.primitives import Latest, Slug


@runtime_checkable
class InvestigationRepository(Protocol):
    def add_investigation(self, investigation: InvestigationRecord) -> None: ...

    def investigation(self, key: Slug) -> InvestigationRecord | None: ...

    def has_entries(self, investigation: Slug) -> bool: ...

    def entries(self, investigation: Slug) -> list[LedgerRecord]: ...

    def unrecorded(self, investigations: Collection[Slug]) -> list[Slug]: ...

    def latest_rounds(self) -> Latest[LatestRound]: ...

    def append(self, investigation: Slug, records: Sequence[LedgerRecord]) -> None: ...
