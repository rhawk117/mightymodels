"""The investigation repository kept in memory."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.investigations.errors import (
    DuplicateInvestigationError,
    InvestigationNotFoundError,
)
from mightymodels_core.investigations.records import (
    ENTRIES,
    INVESTIGATIONS_LISTED,
    duplicate_entry_error,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from mightymodels_core.investigations.records import (
        InvestigationRecord,
        LatestRound,
        LedgerRecord,
    )
    from mightymodels_core.primitives import Latest, Slug


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationLedger:
    investigations: dict[Slug, InvestigationRecord] = field(default_factory=dict)
    entries: dict[Slug, list[LedgerRecord]] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeInvestigationRepository:
    ledger: InvestigationLedger

    def add_investigation(self, investigation: InvestigationRecord) -> None:
        if investigation.key in self.ledger.investigations:
            raise DuplicateInvestigationError(investigation_key=investigation.key)

        self.ledger.investigations[investigation.key] = investigation
        self.ledger.entries[investigation.key] = []

    def has_entries(self, investigation: Slug) -> bool:
        return bool(self.ledger.entries.get(investigation))

    def entries(self, investigation: Slug) -> list[LedgerRecord]:
        held = self.ledger.entries.get(investigation, [])
        if (error := ENTRIES.error(held, owner=f'investigation {investigation}')) is not None:
            raise error
        return sorted(held, key=lambda record: record.seq)

    def unrecorded(self, investigations: Collection[Slug]) -> list[Slug]:
        return [slug for slug in investigations if slug not in self.ledger.investigations]

    def latest_rounds(self) -> Latest[LatestRound]:
        newest_first = [
            (slug, max(record.round for record in held))
            for slug, held in reversed(self.ledger.entries.items())
            if held
        ]
        return INVESTIGATIONS_LISTED.latest(newest_first)

    def append(self, investigation: Slug, records: Sequence[LedgerRecord]) -> None:
        if investigation not in self.ledger.investigations:
            raise InvestigationNotFoundError(investigation_key=investigation)

        held = self.ledger.entries[investigation]
        held_seqs = [record.seq for record in held]
        if (duplicate := duplicate_entry_error(investigation, held_seqs, records)) is not None:
            raise duplicate

        total = len(held) + len(records)
        if (
            error := ENTRIES.write_error(total, owner=f'investigation {investigation}')
        ) is not None:
            raise error

        held.extend(records)
