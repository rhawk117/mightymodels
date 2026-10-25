"""The values, harnesses and builders the investigation tests share."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest
from mightymodels_core.investigations import (
    IncomingEntry,
    InvestigationRecord,
    Ledger,
    LedgerRecord,
)
from mightymodels_core.primitives import Slug, redact

if TYPE_CHECKING:
    from _pytest.mark import ParameterSet
    from mightymodels_core.investigations import InvestigationRepository, InvestigationService
    from mightymodels_core.schemas.investigations import EntryKind, EntrySource

    from tests.core.investigations.fakes import FakeInvestigationRepository
    from tests.core.primitives.clock import FakeClock
    from tests.core.similarity.fakes import FakeSimilarityRepository

SQL = files('mightymodels_core.sql')
FIRST = Slug('first-look')
SECOND = Slug('second-look')
UNADDED = Slug('never-added')
STARTED = Slug('20260506-retry-policy')
MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
HEAD = 'abc1234'


@dataclass(slots=True, kw_only=True, frozen=True)
class InvestigationHarness:
    investigations: InvestigationRepository


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceHarness:
    service: InvestigationService
    investigations: FakeInvestigationRepository
    similarity: FakeSimilarityRepository
    clock: FakeClock


@dataclass(slots=True, kw_only=True, frozen=True)
class Case[Given, Expected]:
    name: str
    given: Given
    expected: Expected

    @property
    def param(self) -> ParameterSet:
        return pytest.param(self, id=self.name)


def create_investigation(key: Slug) -> InvestigationRecord:
    return InvestigationRecord(key=key, target=redact(f'target of {key}'), kind='behavior')


def create_entry(seq: int, *, round_number: int = 1, day: int = 2) -> LedgerRecord:
    return LedgerRecord(
        seq=seq,
        round=round_number,
        kind='known',
        text=redact(f'entry {seq}'),
        source='code-scout',
        cite=redact(f'src/file.py:{seq}'),
        supersedes=(seq - 1,) if seq > 1 else (),
        at=datetime(2026, 1, day, 3, 4, 5, tzinfo=UTC),
        head='abc1234',
    )


def create_incoming(
    kind: EntryKind = 'known',
    *,
    text: str = 'a fact',
    source: EntrySource = 'code-scout',
    cite: str | None = 'src/a.py:1',
    supersedes: tuple[int, ...] = (),
) -> IncomingEntry:
    return IncomingEntry(kind=kind, text=text, source=source, cite=cite, supersedes=supersedes)


def create_ledger(*records: LedgerRecord) -> Ledger:
    return Ledger(investigation=create_investigation(FIRST), records=records)
