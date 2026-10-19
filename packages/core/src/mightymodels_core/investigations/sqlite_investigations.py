"""The investigation repository over a core unit, working within one repository id."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.investigations.errors import (
    DuplicateInvestigationError,
    InvestigationNotFoundError,
)
from mightymodels_core.investigations.records import (
    ENTRIES,
    INVESTIGATIONS_LISTED,
    LedgerRecord,
    duplicate_entry_error,
)
from mightymodels_core.primitives import Slug, redact
from mightymodels_core.schemas.investigations import (
    ADD_INVESTIGATION,
    APPEND_LEDGER_ENTRY,
    INVESTIGATION_BY_KEY,
    LATEST_ROUNDS,
    LEDGER_ENTRIES,
    LEDGER_ENTRY_COUNT,
    RECORDED_INVESTIGATION_KEYS,
    AddInvestigationParams,
    AppendLedgerEntryParams,
    InvestigationIdParams,
    InvestigationKeyParams,
    LatestRoundsParams,
    LedgerEntriesParams,
    RecordedKeysParams,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from mightymodels_core.database import Unit
    from mightymodels_core.investigations.records import InvestigationRecord, LatestRound
    from mightymodels_core.primitives import Latest
    from mightymodels_core.schemas.investigations import LedgerEntryRow


def record_of(row: LedgerEntryRow) -> LedgerRecord:
    return LedgerRecord(
        seq=row.seq,
        round=row.round,
        kind=row.kind,
        text=redact(row.text),
        source=row.source,
        cite=None if row.cite is None else redact(row.cite),
        supersedes=tuple(row.supersedes),
        at=row.at,
        head=row.head,
    )


def entry_params_of(investigation_id: int, record: LedgerRecord) -> AppendLedgerEntryParams:
    return AppendLedgerEntryParams(
        investigation_id=investigation_id,
        seq=record.seq,
        round=record.round,
        kind=record.kind,
        text=record.text,
        source=record.source,
        cite=record.cite,
        supersedes=list(record.supersedes),
        at=record.at,
        head=record.head,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteInvestigationRepository:
    unit: Unit
    repository_id: int

    def add_investigation(self, investigation: InvestigationRecord) -> None:
        if self.investigation_id(investigation.key) is not None:
            raise DuplicateInvestigationError(investigation_key=investigation.key)

        params = AddInvestigationParams(
            repository_id=self.repository_id,
            investigation_key=investigation.key,
            target=investigation.target,
            kind=investigation.kind,
        )
        self.unit.one(ADD_INVESTIGATION, params)

    def has_entries(self, investigation: Slug) -> bool:
        investigation_id = self.investigation_id(investigation)
        if investigation_id is None:
            return False

        row = self.unit.one(
            LEDGER_ENTRY_COUNT, InvestigationIdParams(investigation_id=investigation_id)
        )
        return row is not None and row.count > 0

    def entries(self, investigation: Slug) -> list[LedgerRecord]:
        investigation_id = self.investigation_id(investigation)
        if investigation_id is None:
            return []

        rows = self.entry_rows(investigation, investigation_id)
        return [record_of(row) for row in rows]

    def unrecorded(self, investigations: Collection[Slug]) -> list[Slug]:
        params = RecordedKeysParams(
            repository_id=self.repository_id, investigation_keys=list(investigations)
        )
        recorded = {
            row.investigation_key for row in self.unit.all(RECORDED_INVESTIGATION_KEYS, params)
        }
        return [slug for slug in investigations if slug not in recorded]

    def latest_rounds(self) -> Latest[LatestRound]:
        params = LatestRoundsParams(
            repository_id=self.repository_id, limit=INVESTIGATIONS_LISTED.fetched
        )
        rows = self.unit.all(LATEST_ROUNDS, params)
        newest_first = [(Slug(row.investigation_key), row.round) for row in rows]
        return INVESTIGATIONS_LISTED.latest(newest_first)

    def append(self, investigation: Slug, records: Sequence[LedgerRecord]) -> None:
        investigation_id = self.investigation_id(investigation)
        if investigation_id is None:
            raise InvestigationNotFoundError(investigation_key=investigation)

        held = self.entry_rows(investigation, investigation_id)
        held_seqs = [row.seq for row in held]
        if (duplicate := duplicate_entry_error(investigation, held_seqs, records)) is not None:
            raise duplicate

        total = len(held) + len(records)
        if (
            error := ENTRIES.write_error(total, owner=f'investigation {investigation}')
        ) is not None:
            raise error

        batch = [entry_params_of(investigation_id, record) for record in records]
        self.unit.run_many(APPEND_LEDGER_ENTRY, batch)

    def investigation_id(self, investigation: Slug) -> int | None:
        params = InvestigationKeyParams(
            repository_id=self.repository_id, investigation_key=investigation
        )
        row = self.unit.one(INVESTIGATION_BY_KEY, params)
        return None if row is None else row.id

    def entry_rows(self, investigation: Slug, investigation_id: int) -> list[LedgerEntryRow]:
        params = LedgerEntriesParams(investigation_id=investigation_id, limit=ENTRIES.fetched)
        rows = self.unit.all(LEDGER_ENTRIES, params)
        if (error := ENTRIES.error(rows, owner=f'investigation {investigation}')) is not None:
            raise error
        return rows
