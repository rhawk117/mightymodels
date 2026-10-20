"""Every rule a crashout entry is refused by, and the record built from one that passes.

The caller asks the policy; it reads no repository and no clock, and the time the server received
the entry is a value passed in. An entry is refused for no failures, then for the first blank text
among the rant, the failures, the root cause and the corrective action. The rant keeps its words
and loses its line endings; the root cause and the corrective action lose the whitespace around
them. Every free-text field is redacted within its limit when the record is built, and one that
redaction lengthens past its limit refuses the crashout.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.crashouts.errors import BlankCrashoutFieldError, NoFailuresError
from mightymodels_core.crashouts.records import CrashoutRecord
from mightymodels_core.primitives import redact_within

if TYPE_CHECKING:
    from datetime import datetime

    from mightymodels_core.primitives import RedactedText
    from mightymodels_core.schemas.crashouts import CrashoutSeverity, Verdict

type CrashoutIssue = BlankCrashoutFieldError | NoFailuresError


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutOptions:
    name_limit: int = 255
    prose_limit: int = 4000


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutEntry:
    ticket_key: str | None
    branch: str | None
    severity: CrashoutSeverity
    verdict: Verdict
    rant: str
    failures: tuple[str, ...]
    root_cause: str
    corrective_action: str
    barked_back: bool


def normalized_rant(rant: str) -> str:
    lines = rant.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    return '\n'.join(line.rstrip() for line in lines).strip('\n')


@dataclass(slots=True, kw_only=True, frozen=True)
class CrashoutPolicy:
    entry: CrashoutEntry
    options: CrashoutOptions

    @property
    def has_failures(self) -> bool:
        return bool(self.entry.failures)

    @property
    def named_texts(self) -> list[tuple[str, str]]:
        failures = [('failures', failure) for failure in self.entry.failures]
        return [
            ('rant', self.entry.rant),
            *failures,
            ('root_cause', self.entry.root_cause),
            ('corrective_action', self.entry.corrective_action),
        ]

    @property
    def blank_field(self) -> str | None:
        return next((name for name, text in self.named_texts if not text.strip()), None)

    def get_entry_problem(self) -> CrashoutIssue | None:
        if not self.has_failures:
            return NoFailuresError()

        if (blank := self.blank_field) is not None:
            return BlankCrashoutFieldError(field=blank)

        return None

    def redacted_text(self, text: str, field: str) -> RedactedText:
        return redact_within(text, field, self.options.prose_limit)

    def crashout_record(self, at: datetime) -> CrashoutRecord:
        entry = self.entry
        branch = None
        if entry.branch is not None:
            branch = redact_within(entry.branch, 'branch', self.options.name_limit)
        return CrashoutRecord(
            at=at,
            ticket_key=entry.ticket_key,
            branch=branch,
            severity=entry.severity,
            verdict=entry.verdict,
            rant=self.redacted_text(normalized_rant(entry.rant), 'rant'),
            failures=tuple(self.redacted_text(failure, 'failures') for failure in entry.failures),
            root_cause=self.redacted_text(entry.root_cause.strip(), 'root_cause'),
            corrective_action=self.redacted_text(
                entry.corrective_action.strip(), 'corrective_action'
            ),
            barked_back=entry.barked_back,
        )
