"""The investigation service: start, add entries, render, knowns and list rounds.

It takes values and returns values. The caller passes HEAD in, wraps a call in its unit of work and
words the response; the service never touches git, a process or the filesystem. The target and
every entry it appends go to the similarity repository.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mightymodels_core.investigations.ledger import (
    recorded_ledger,
    written_entry,
    written_target,
)
from mightymodels_core.investigations.policy import (
    BatchPolicy,
    EntryStamp,
    InvestigationOptions,
    NamePolicy,
)
from mightymodels_core.investigations.records import InvestigationRecord
from mightymodels_core.primitives import Slug, redact_within

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.investigations.ledger import Knowns, KnownsSelection, Ledger
    from mightymodels_core.investigations.policy import IncomingEntry
    from mightymodels_core.investigations.records import LatestRound, TargetKind
    from mightymodels_core.investigations.repository import InvestigationRepository
    from mightymodels_core.primitives import Clock, Latest
    from mightymodels_core.similarity.records import Duplicate
    from mightymodels_core.similarity.repository import SimilarityRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class StartRequest:
    target: str
    kind: TargetKind


@dataclass(slots=True, kw_only=True, frozen=True)
class AddRequest:
    round: int
    entries: Sequence[IncomingEntry]
    head: str | None


@dataclass(slots=True, kw_only=True, frozen=True)
class Started:
    investigation: Slug
    duplicates: tuple[Duplicate, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class Added:
    investigation: Slug
    seqs: tuple[int, ...]
    redactions: int
    duplicates: tuple[Duplicate, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationService:
    investigations: InvestigationRepository
    similarity: SimilarityRepository
    clock: Clock
    options: InvestigationOptions = field(default_factory=InvestigationOptions)

    def free_key(self, naming: NamePolicy) -> Slug:
        keys = map(Slug, naming.names())
        return next(key for key in keys if self.investigations.investigation(key) is None)

    def start(self, request: StartRequest) -> Started:
        target = redact_within(request.target, 'target', self.options.prose_limit)
        naming = NamePolicy(target=target, day=self.clock.now(), options=self.options)
        key = self.free_key(naming)
        self.investigations.add_investigation(
            InvestigationRecord(key=key, target=target, kind=request.kind)
        )
        duplicates = self.similarity.record_all([written_target(key, target)])
        return Started(investigation=key, duplicates=tuple(duplicates))

    def add(self, investigation: Slug, request: AddRequest) -> Added:
        ledger = recorded_ledger(self.investigations, investigation)
        policy = BatchPolicy(
            latest_round=ledger.latest_round,
            supersedable=ledger.supersedable,
            stamp=EntryStamp(round=request.round, at=self.clock.now(), head=request.head),
            entries=request.entries,
            options=self.options,
        )
        if problem := policy.get_batch_problem():
            raise problem

        redacted = policy.redacted_records(ledger.next_seq)
        records = [item.record for item in redacted]
        self.investigations.append(investigation, records)
        writes = [written_entry(investigation, record) for record in records]
        return Added(
            investigation=investigation,
            seqs=tuple(record.seq for record in records),
            redactions=sum(item.hits for item in redacted),
            duplicates=tuple(self.similarity.record_all(writes)),
        )

    def render(self, investigation: Slug) -> Ledger:
        return recorded_ledger(self.investigations, investigation)

    def knowns(self, investigation: Slug, selection: KnownsSelection, head: str | None) -> Knowns:
        ledger = recorded_ledger(self.investigations, investigation)
        return ledger.knowns(selection, head)

    def list_rounds(self) -> Latest[LatestRound]:
        return self.investigations.latest_rounds()
