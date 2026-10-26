"""The session pointer a hook records and reads, and how long one is kept."""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from mightymodels_core.schemas.session_pointers import PointerKind

POINTER_RETENTION = timedelta(days=30)


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionPointer:
    kind: PointerKind
    key: str
    written_at: datetime
