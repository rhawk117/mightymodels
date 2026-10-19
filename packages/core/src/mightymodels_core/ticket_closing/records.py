"""The closing record the repository hands out: a frozen value, never a database row.

The prose fields are redacted text, which only `redact` produces, so a secret cannot reach a
closing by the type alone.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText


@dataclass(slots=True, kw_only=True, frozen=True)
class ClosingRecord:
    closed_at: datetime
    head: str | None
    shipped: RedactedText
    pr: str | None
    gotchas: tuple[RedactedText, ...]
    archive: str
