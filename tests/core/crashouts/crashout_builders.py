"""The values, harnesses and builders the crashout tests share."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from typing import TYPE_CHECKING

from mightymodels_core.crashouts import CrashoutEntry, CrashoutRecord
from mightymodels_core.primitives import redact

if TYPE_CHECKING:
    from mightymodels_core.crashouts import CrashoutRepository, CrashoutService

    from tests.core.crashouts.fakes import FakeCrashoutRepository
    from tests.core.primitives.clock import FakeClock
    from tests.core.similarity.fakes import FakeSimilarityRepository

SQL = files('mightymodels_core.sql')
FIRST_AT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
MOMENT = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutHarness:
    crashouts: CrashoutRepository


def create_crashout(index: int = 0, *, branch: str | None = 'feat/retry') -> CrashoutRecord:
    return CrashoutRecord(
        at=FIRST_AT + timedelta(seconds=index),
        ticket_key='ENT-1',
        branch=None if branch is None else redact(branch),
        severity='heated',
        verdict='split',
        rant=redact(f'rant {index}'),
        failures=(redact('pytest failed'), redact('ruff failed')),
        root_cause=redact(f'root cause {index}'),
        corrective_action=redact('read the failing output first'),
        barked_back=False,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class ServiceHarness:
    service: CrashoutService
    crashouts: FakeCrashoutRepository
    similarity: FakeSimilarityRepository
    clock: FakeClock


def create_entry(
    *,
    rant: str = 'WHY did you skip the tests',
    failures: tuple[str, ...] = ('skipped the tests', 'claimed done'),
    root_cause: str = 'optimised for speed',
    corrective_action: str = 'run the gate before reporting',
    branch: str | None = 'fix/retry-queue',
) -> CrashoutEntry:
    return CrashoutEntry(
        ticket_key='retry-queue',
        branch=branch,
        severity='heated',
        verdict='deserved',
        rant=rant,
        failures=failures,
        root_cause=root_cause,
        corrective_action=corrective_action,
        barked_back=False,
    )
