"""The values the investigation repository hands out and takes in: frozen, never a database row.

An `InvestigationRecord` is what adding an investigation writes. A `LedgerRecord` is one entry of
its ledger. The target and every entry's text and cite are redacted text, which only `redact`
produces, so a secret cannot reach the ledger by the type alone.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from mightymodels_core.investigations.errors import DuplicateEntryError
from mightymodels_core.primitives import ReadLimit

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText, Slug
    from mightymodels_core.vocabulary.investigations import EntryKind, EntrySource

type TargetKind = Literal['behavior', 'claim', 'research', 'change']
type LatestRound = tuple[Slug, int]

ENTRIES = ReadLimit(rows=2000, kept='ledger entries')
INVESTIGATIONS_LISTED = ReadLimit(rows=100, kept='investigations')


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationRecord:
    key: Slug
    target: RedactedText
    kind: TargetKind


@dataclass(slots=True, kw_only=True, frozen=True)
class LedgerRecord:
    seq: int
    round: int
    kind: EntryKind
    text: RedactedText
    source: EntrySource
    cite: RedactedText | None
    supersedes: tuple[int, ...]
    at: datetime
    head: str | None


def duplicate_entry_error(
    investigation: Slug, held_seqs: Collection[int], records: Sequence[LedgerRecord]
) -> DuplicateEntryError | None:
    seen = set(held_seqs)
    for record in records:
        if record.seq in seen:
            return DuplicateEntryError(investigation_key=investigation, seq=record.seq)

        seen.add(record.seq)
    return None
