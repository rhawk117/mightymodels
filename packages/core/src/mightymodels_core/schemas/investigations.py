"""The investigation rows and their ledger entries."""

from datetime import datetime
from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Command, Query
from mightymodels_core.vocabulary.investigations import EntryKind, EntrySource

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class AddInvestigationParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    investigation_key: str
    target: str
    kind: str


class InvestigationKeyParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    investigation_key: str


class RecordedKeysParams(Struct, frozen=True, kw_only=True):
    repository_id: int
    investigation_keys: list[str]


class AppendLedgerEntryParams(Struct, frozen=True, kw_only=True):
    investigation_id: int
    seq: int
    round: int
    kind: EntryKind
    text: str
    source: EntrySource
    cite: str | None
    supersedes: list[int]
    at: datetime
    head: str | None


class LedgerEntriesParams(Struct, frozen=True, kw_only=True, gc=False):
    investigation_id: int
    limit: int


class InvestigationIdParams(Struct, frozen=True, kw_only=True, gc=False):
    investigation_id: int


class LatestRoundsParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    limit: int


class InvestigationIdRow(Struct, frozen=True, kw_only=True, gc=False):
    id: int


class InvestigationRow(Struct, frozen=True, kw_only=True):
    id: int
    investigation_key: str
    target: str
    kind: str
    created_at: datetime


class InvestigationKeyRow(Struct, frozen=True, kw_only=True, gc=False):
    investigation_key: str


class LedgerEntryRow(Struct, frozen=True, kw_only=True):
    seq: int
    round: int
    kind: EntryKind
    text: str
    source: EntrySource
    cite: str | None
    supersedes: list[int]
    at: datetime
    head: str | None


class EntryCountRow(Struct, frozen=True, kw_only=True, gc=False):
    count: int


class LatestRoundRow(Struct, frozen=True, kw_only=True, gc=False):
    investigation_key: str
    round: int


ADD_INVESTIGATION = Query(
    name='add_investigation', params=AddInvestigationParams, row=InvestigationIdRow
)
INVESTIGATION_BY_KEY = Query(
    name='investigation_by_key', params=InvestigationKeyParams, row=InvestigationRow
)
RECORDED_INVESTIGATION_KEYS = Query(
    name='recorded_investigation_keys', params=RecordedKeysParams, row=InvestigationKeyRow
)
APPEND_LEDGER_ENTRY = Command(name='append_ledger_entry', params=AppendLedgerEntryParams)
LEDGER_ENTRIES = Query(name='ledger_entries', params=LedgerEntriesParams, row=LedgerEntryRow)
LEDGER_ENTRY_COUNT = Query(
    name='ledger_entry_count', params=InvestigationIdParams, row=EntryCountRow
)
LATEST_ROUNDS = Query(name='latest_rounds', params=LatestRoundsParams, row=LatestRoundRow)

DECLARATIONS: tuple[Declaration, ...] = (
    ADD_INVESTIGATION,
    INVESTIGATION_BY_KEY,
    RECORDED_INVESTIGATION_KEYS,
    APPEND_LEDGER_ENTRY,
    LEDGER_ENTRIES,
    LEDGER_ENTRY_COUNT,
    LATEST_ROUNDS,
)
