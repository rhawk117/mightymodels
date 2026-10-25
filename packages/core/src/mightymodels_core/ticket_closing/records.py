"""The closing record the repository hands out and the facts the close service is given.

The prose fields are redacted text, which only `redact` produces, so a secret cannot reach a
closing by the type alone. `CloseFacts` is what the caller learned from git and the disk: why git
was not consulted, HEAD, the ticket branch and whether the debug note is still there.
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


@dataclass(slots=True, kw_only=True, frozen=True)
class BranchFacts:
    exists: bool
    unpushed: int | None
    checked_out: bool
    dirty: int | None


@dataclass(slots=True, kw_only=True, frozen=True)
class CloseFacts:
    debug_note: bool
    git_refusal: str | None
    head: str | None
    branch: BranchFacts | None


@dataclass(slots=True, kw_only=True, frozen=True)
class ClosingLines:
    shipped: str
    pr: str | None
    gotchas: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class OneLinedClosing:
    shipped: RedactedText
    pr: RedactedText | None
    gotchas: tuple[RedactedText, ...]
