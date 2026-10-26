"""The pointer from a Claude Code session to the ticket or investigation it last worked in."""

from typing import TYPE_CHECKING, Literal

from msgspec import Struct

from mightymodels_core.database import Command, Query

if TYPE_CHECKING:
    from mightymodels_core.database import Declaration

type PointerKind = Literal['ticket', 'investigation']


class UpsertSessionPointerParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    session_id: str
    kind: PointerKind
    key: str
    written_at: int


class SessionPointerSessionParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    session_id: str


class PruneSessionPointersParams(Struct, frozen=True, kw_only=True, gc=False):
    repository_id: int
    cutoff: int


class SessionPointerRow(Struct, frozen=True, kw_only=True, gc=False):
    kind: PointerKind
    key: str
    written_at: int


UPSERT_SESSION_POINTER = Command(name='upsert_session_pointer', params=UpsertSessionPointerParams)
SESSION_POINTER_OF_SESSION = Query(
    name='session_pointer_of_session',
    params=SessionPointerSessionParams,
    row=SessionPointerRow,
)
PRUNE_SESSION_POINTERS = Command(name='prune_session_pointers', params=PruneSessionPointersParams)

DECLARATIONS: tuple[Declaration, ...] = (
    UPSERT_SESSION_POINTER,
    SESSION_POINTER_OF_SESSION,
    PRUNE_SESSION_POINTERS,
)
