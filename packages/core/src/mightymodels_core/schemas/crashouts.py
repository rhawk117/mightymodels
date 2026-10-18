"""The crashout journal of a repository."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from msgspec import Struct

from mightymodels_core.database import Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration


class Severity(StrEnum):
    MILD_TILT = 'mild-tilt'
    HEATED = 'heated'
    CRASHOUT = 'crashout'
    FULL_MELTDOWN = 'full-meltdown'


class Verdict(StrEnum):
    DESERVED = 'deserved'
    SPLIT = 'split'
    UNREASONABLE = 'unreasonable'


class JournalCrashoutParams(Struct, frozen=True, kw_only=True):
    repository_id: int
    at: datetime
    ticket_key: str | None
    branch: str | None
    severity: Severity
    verdict: Verdict
    rant: str
    failures: list[str]
    root_cause: str
    corrective_action: str
    barked_back: bool


class LatestCrashoutsParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    limit: int


class CrashoutCountParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int


class CrashoutIdRow(Struct, frozen=True, kw_only=True, gc=False):
    id: int


class CrashoutRow(Struct, frozen=True, kw_only=True):
    id: int
    at: datetime
    ticket_key: str | None
    branch: str | None
    severity: Severity
    verdict: Verdict
    rant: str
    failures: list[str]
    root_cause: str
    corrective_action: str
    barked_back: bool


class CrashoutCountRow(Struct, frozen=True, kw_only=True, gc=False):
    count: int


JOURNAL_CRASHOUT = Query(name='journal_crashout', params=JournalCrashoutParams, row=CrashoutIdRow)
LATEST_CRASHOUTS = Query(name='latest_crashouts', params=LatestCrashoutsParams, row=CrashoutRow)
CRASHOUT_COUNT = Query(name='crashout_count', params=CrashoutCountParams, row=CrashoutCountRow)

DECLARATIONS: tuple[Declaration, ...] = (JOURNAL_CRASHOUT, LATEST_CRASHOUTS, CRASHOUT_COUNT)
