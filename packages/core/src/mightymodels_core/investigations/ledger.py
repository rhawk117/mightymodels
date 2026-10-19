"""A ledger as it is read back: the investigation and every entry of it, in the order stored.

Nothing rewrites an entry. One is retired by a later entry that names it in `supersedes`, and
`Ledger.live` is what remains. The target belongs to the investigation, not to the entries, so the
first entry is number 1 and any entry may be retired.

A snapshot and a closing read the ledgers a ticket links, so `ledger_of` takes the repository of
whoever holds the unit of work. It answers `None` for an investigation that was never added, and
`recorded_ledger` is the guard for a caller that needs the ledger to exist. `linked_ledgers` reads
every ledger a ticket links, in the order the ticket links them, and names the links with none.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from mightymodels_core.investigations.errors import UnknownInvestigationError
from mightymodels_core.primitives import Slug
from mightymodels_core.similarity.records import Written

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mightymodels_core.investigations.records import InvestigationRecord, LedgerRecord
    from mightymodels_core.investigations.repository import InvestigationRepository
    from mightymodels_core.primitives import RedactedText
    from mightymodels_core.schemas.investigations import EntryKind

type EntryStatus = Literal['current', 'lead']

SECTION_KINDS: tuple[EntryKind, ...] = ('known', 'open', 'decision', 'resource')
KNOWNS_LIMIT = 40


@dataclass(slots=True, kw_only=True, frozen=True)
class KnownsSelection:
    kinds: tuple[EntryKind, ...] = SECTION_KINDS
    limit: int = KNOWNS_LIMIT


@dataclass(slots=True, kw_only=True, frozen=True)
class KnownRow:
    record: LedgerRecord
    status: EntryStatus


@dataclass(slots=True, kw_only=True, frozen=True)
class Knowns:
    investigation: Slug
    head: str | None
    rows: tuple[KnownRow, ...]
    hidden: int


@dataclass(slots=True, kw_only=True, frozen=True)
class LedgerSection:
    kind: EntryKind
    records: tuple[LedgerRecord, ...]


def entry_reference(investigation: Slug, seq: int) -> str:
    return f'{investigation} e{seq}'


def written_target(investigation: Slug, target: RedactedText) -> Written:
    return Written(kind='ledger-entry', reference=f'{investigation} target', text=target)


def written_entry(investigation: Slug, record: LedgerRecord) -> Written:
    reference = entry_reference(investigation, record.seq)
    return Written(kind='ledger-entry', reference=reference, text=record.text)


def entry_status(record: LedgerRecord, head: str | None) -> EntryStatus:
    stored_at_head = head is not None and record.head == head
    return 'current' if stored_at_head else 'lead'


@dataclass(slots=True, kw_only=True, frozen=True)
class Ledger:
    investigation: InvestigationRecord
    records: tuple[LedgerRecord, ...]

    @property
    def key(self) -> Slug:
        return self.investigation.key

    @property
    def next_seq(self) -> int:
        return len(self.records) + 1

    @property
    def latest_round(self) -> int:
        return max((record.round for record in self.records), default=0)

    @property
    def live(self) -> tuple[LedgerRecord, ...]:
        retired = {seq for record in self.records for seq in record.supersedes}
        return tuple(record for record in self.records if record.seq not in retired)

    @property
    def supersedable(self) -> frozenset[int]:
        return frozenset(record.seq for record in self.records)

    @property
    def next_questions(self) -> tuple[LedgerRecord, ...]:
        latest = self.latest_round
        return tuple(record for record in self.live_of_kind('next') if record.round == latest)

    @property
    def sections(self) -> tuple[LedgerSection, ...]:
        return tuple(
            LedgerSection(kind=kind, records=self.live_of_kind(kind)) for kind in SECTION_KINDS
        )

    def live_of_kind(self, kind: EntryKind) -> tuple[LedgerRecord, ...]:
        return tuple(record for record in self.live if record.kind == kind)

    def origin_of(self, record: LedgerRecord) -> str:
        return entry_reference(self.key, record.seq)

    def knowns(self, selection: KnownsSelection, head: str | None) -> Knowns:
        selected = [record for record in self.live if record.kind in selection.kinds]
        shown = selected[: selection.limit]
        return Knowns(
            investigation=self.key,
            head=head,
            rows=tuple(
                KnownRow(record=record, status=entry_status(record, head)) for record in shown
            ),
            hidden=len(selected) - len(shown),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class LinkedLedgers:
    ledgers: tuple[Ledger, ...]
    missing: tuple[Slug, ...]


def ledger_of(investigations: InvestigationRepository, key: Slug) -> Ledger | None:
    investigation = investigations.investigation(key)
    if investigation is None:
        return None

    return Ledger(investigation=investigation, records=tuple(investigations.entries(key)))


def linked_ledgers(investigations: InvestigationRepository, linked: Iterable[str]) -> LinkedLedgers:
    read = {name: ledger_of(investigations, name) for name in map(Slug, dict.fromkeys(linked))}
    return LinkedLedgers(
        ledgers=tuple(ledger for ledger in read.values() if ledger is not None),
        missing=tuple(name for name, ledger in read.items() if ledger is None),
    )


def recorded_ledger(investigations: InvestigationRepository, key: Slug) -> Ledger:
    ledger = ledger_of(investigations, key)
    if ledger is None:
        raise UnknownInvestigationError(investigation_key=key)

    return ledger
