"""Arguments and results of the `investigation` tool.

`LedgerEntry` is one entry as a caller hands it to `add`. The tool numbers it, stamps it with the
round, the time and HEAD, and stores it; the target is the first entry of every ledger and only
`start` writes it.

`InvestigationRequest` is what an action needs beyond the investigation and the entries: the
target and its kind for `start`, the round for `add`, the kinds and the limit for `knowns`.
"""

from enum import StrEnum, auto
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DEFAULT_KNOWNS_LIMIT = 40

type Cite = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
type KnownsLimit = Annotated[int, Field(ge=1)]


class InvestigationAction(StrEnum):
    START = auto()
    ADD = auto()
    RENDER = auto()
    KNOWNS = auto()
    LIST = auto()


class EntryKind(StrEnum):
    TARGET = auto()
    KNOWN = auto()
    OPEN = auto()
    DECISION = auto()
    RESOURCE = auto()
    NEXT = auto()


class TargetKind(StrEnum):
    BEHAVIOR = auto()
    CLAIM = auto()
    RESEARCH = auto()
    CHANGE = auto()


class Source(StrEnum):
    CODE_SCOUT = 'code-scout'
    WEB_SCOUT = 'web-scout'
    USER = 'user'
    PRIMARY = 'primary'


type TableKind = Literal[EntryKind.KNOWN, EntryKind.OPEN, EntryKind.DECISION, EntryKind.RESOURCE]
type TableKinds = Annotated[tuple[TableKind, ...], Field(min_length=1)]

TABLE_KINDS: tuple[TableKind, ...] = (
    EntryKind.KNOWN,
    EntryKind.OPEN,
    EntryKind.DECISION,
    EntryKind.RESOURCE,
)


class LedgerEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    kind: EntryKind
    text: str
    source: Source
    cite: Cite | None = None
    supersedes: tuple[int, ...] = ()


class InvestigationStart(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    target: str
    kind: TargetKind


class LedgerRound(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    round: int


class KnownsFilter(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    kinds: TableKinds = TABLE_KINDS
    limit: KnownsLimit = DEFAULT_KNOWNS_LIMIT


type InvestigationRequest = InvestigationStart | LedgerRound | KnownsFilter


class InvestigationView(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    investigation_id: str | None = None
