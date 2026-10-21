"""The value the crashout repository hands out and takes in: frozen, never a database row.

The branch, rant, each failure, root cause and corrective action are redacted text, which only
`redact` produces, so a secret cannot reach the journal by the type alone. The ticket key,
severity, verdict and barked_back flag are plain.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import ReadLimit

if TYPE_CHECKING:
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText
    from mightymodels_core.vocabulary.crashouts import CrashoutSeverity, Verdict

JOURNAL_WINDOW = ReadLimit(rows=100, kept='crashouts')


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutRecord:
    at: datetime
    ticket_key: str | None
    branch: RedactedText | None
    severity: CrashoutSeverity
    verdict: Verdict
    rant: RedactedText
    failures: tuple[RedactedText, ...]
    root_cause: RedactedText
    corrective_action: RedactedText
    barked_back: bool
