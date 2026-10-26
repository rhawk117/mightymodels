"""The session pointer repository over a core unit."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import from_unixepoch
from mightymodels_core.schemas.session_pointers import (
    PRUNE_SESSION_POINTERS,
    SESSION_POINTER_OF_SESSION,
    UPSERT_SESSION_POINTER,
    PruneSessionPointersParams,
    SessionPointerSessionParams,
    UpsertSessionPointerParams,
)
from mightymodels_core.session_pointers.records import POINTER_RETENTION, SessionPointer

if TYPE_CHECKING:
    from mightymodels_core.database import Unit
    from mightymodels_core.primitives import Clock
    from mightymodels_core.schemas.session_pointers import PointerKind


@dataclass(slots=True, kw_only=True, frozen=True)
class SqliteSessionPointerRepository:
    unit: Unit
    repository_id: int
    clock: Clock

    def record(self, session_id: str, kind: PointerKind, key: str) -> None:
        params = UpsertSessionPointerParams(
            repository_id=self.repository_id,
            session_id=session_id,
            kind=kind,
            key=key,
            written_at=int(self.clock.now().timestamp()),
        )
        self.unit.run(UPSERT_SESSION_POINTER, params)

    def lookup(self, session_id: str) -> SessionPointer | None:
        params = SessionPointerSessionParams(
            repository_id=self.repository_id, session_id=session_id
        )
        row = self.unit.one(SESSION_POINTER_OF_SESSION, params)
        if row is None:
            return None
        return SessionPointer(kind=row.kind, key=row.key, written_at=from_unixepoch(row.written_at))

    def prune(self) -> int:
        cutoff = int((self.clock.now() - POINTER_RETENTION).timestamp())
        params = PruneSessionPointersParams(repository_id=self.repository_id, cutoff=cutoff)
        return self.unit.run(PRUNE_SESSION_POINTERS, params)
