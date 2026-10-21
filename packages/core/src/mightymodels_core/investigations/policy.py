"""Every rule an entry batch and an investigation name are refused by or built from.

The caller reads the ledger and asks a policy; the policy reads no repository and no clock, and the
moment and HEAD are values passed in. A batch is refused for a round before the latest, then for
the first entry that breaks a rule, so one refused entry refuses the batch. An entry is refused for
empty text, then for a missing cite, then for a source its kind does not allow, then for superseding
an entry the ledger does not hold. Text and cite are redacted within the prose limit when the
records are built, and the hits are counted.
"""

import re
from dataclasses import dataclass, field
from itertools import count
from typing import TYPE_CHECKING

from mightymodels_core.investigations.errors import (
    CiteRequiredError,
    EmptyTextError,
    RoundRegressionError,
    SourceNotAllowedError,
    UnknownSupersededError,
)
from mightymodels_core.investigations.records import LedgerRecord
from mightymodels_core.primitives import redaction_within

if TYPE_CHECKING:
    from collections.abc import Collection, Iterator, Sequence
    from datetime import datetime

    from mightymodels_core.investigations.errors import InvalidEntryError
    from mightymodels_core.vocabulary.investigations import EntryKind, EntrySource

type EntryRules = dict[EntryKind, EntryRule]
type BatchIssue = RoundRegressionError | InvalidEntryError

OUTSIDE_A_NAME = re.compile(r'[^a-z0-9]+')
ANY_SOURCE: frozenset[EntrySource] = frozenset({'code-scout', 'web-scout', 'user', 'primary'})


@dataclass(slots=True, kw_only=True, frozen=True)
class EntryRule:
    needs_cite: bool
    sources: frozenset[EntrySource]


def create_entry_rules() -> EntryRules:
    return {
        'known': EntryRule(needs_cite=True, sources=ANY_SOURCE),
        'open': EntryRule(needs_cite=False, sources=ANY_SOURCE),
        'decision': EntryRule(needs_cite=False, sources=frozenset({'user'})),
        'resource': EntryRule(needs_cite=True, sources=ANY_SOURCE),
        'next': EntryRule(needs_cite=False, sources=frozenset({'code-scout', 'web-scout', 'user'})),
    }


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationOptions:
    day_format: str = '%Y%m%d'
    name_limit: int = 40
    unnamed_target: str = 'investigation'
    prose_limit: int = 4000
    rules: EntryRules = field(default_factory=create_entry_rules)


@dataclass(slots=True, kw_only=True, frozen=True)
class IncomingEntry:
    kind: EntryKind
    text: str
    source: EntrySource
    cite: str | None = None
    supersedes: tuple[int, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class EntryStamp:
    round: int
    at: datetime
    head: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class RedactedRecord:
    record: LedgerRecord
    hits: int


@dataclass(slots=True, kw_only=True, frozen=True)
class EntryPolicy:
    index: int
    entry: IncomingEntry
    supersedable: Collection[int]
    options: InvestigationOptions = field(default_factory=InvestigationOptions)

    @property
    def rule(self) -> EntryRule:
        return self.options.rules[self.entry.kind]

    @property
    def is_empty(self) -> bool:
        return not self.entry.text.strip()

    @property
    def lacks_cite(self) -> bool:
        return self.rule.needs_cite and self.entry.cite is None

    @property
    def has_allowed_source(self) -> bool:
        return self.entry.source in self.rule.sources

    @property
    def unknown_superseded(self) -> list[int]:
        return sorted(set(self.entry.supersedes) - set(self.supersedable))

    def get_entry_problem(self) -> InvalidEntryError | None:
        if self.is_empty:
            return EmptyTextError(index=self.index)

        if self.lacks_cite:
            return CiteRequiredError(index=self.index, kind=self.entry.kind)

        if not self.has_allowed_source:
            return SourceNotAllowedError(
                index=self.index, kind=self.entry.kind, source=self.entry.source
            )

        if unknown := self.unknown_superseded:
            return UnknownSupersededError(index=self.index, unknown=unknown)

        return None

    def redacted_record(self, seq: int, stamp: EntryStamp) -> RedactedRecord:
        limit = self.options.prose_limit
        text = redaction_within(self.entry.text, 'text', limit)
        cite = None if self.entry.cite is None else redaction_within(self.entry.cite, 'cite', limit)
        cite_text = None if cite is None else cite.text
        cite_hits = 0 if cite is None else cite.hits
        record = LedgerRecord(
            seq=seq,
            round=stamp.round,
            kind=self.entry.kind,
            text=text.text,
            source=self.entry.source,
            cite=cite_text,
            supersedes=self.entry.supersedes,
            at=stamp.at,
            head=stamp.head,
        )
        return RedactedRecord(record=record, hits=text.hits + cite_hits)


@dataclass(slots=True, kw_only=True, frozen=True)
class BatchPolicy:
    latest_round: int
    supersedable: Collection[int]
    stamp: EntryStamp
    entries: Sequence[IncomingEntry]
    options: InvestigationOptions = field(default_factory=InvestigationOptions)

    @property
    def policies(self) -> list[EntryPolicy]:
        return [
            EntryPolicy(
                index=index,
                entry=entry,
                supersedable=self.supersedable,
                options=self.options,
            )
            for index, entry in enumerate(self.entries)
        ]

    @property
    def first_entry_problem(self) -> InvalidEntryError | None:
        problems = (policy.get_entry_problem() for policy in self.policies)
        return next((problem for problem in problems if problem is not None), None)

    def get_batch_problem(self) -> BatchIssue | None:
        if self.stamp.round < self.latest_round:
            return RoundRegressionError(given=self.stamp.round, latest=self.latest_round)

        return self.first_entry_problem

    def redacted_records(self, first_seq: int) -> list[RedactedRecord]:
        numbered = enumerate(self.policies, start=first_seq)
        return [policy.redacted_record(seq, self.stamp) for seq, policy in numbered]


@dataclass(slots=True, kw_only=True, frozen=True)
class NamePolicy:
    target: str
    day: datetime
    options: InvestigationOptions = field(default_factory=InvestigationOptions)

    @property
    def target_name(self) -> str:
        limit = self.options.name_limit
        name = OUTSIDE_A_NAME.sub('-', self.target.lower()).strip('-')
        if len(name) > limit:
            name = name[: limit + 1].rsplit('-', 1)[0][:limit]
        return name or self.options.unnamed_target

    @property
    def stem(self) -> str:
        return f'{self.day.strftime(self.options.day_format)}-{self.target_name}'

    def names(self) -> Iterator[str]:
        return (self.stem if repeat == 1 else f'{self.stem}-{repeat}' for repeat in count(1))
