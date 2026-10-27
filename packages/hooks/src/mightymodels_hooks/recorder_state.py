"""Writing one dialog's answers as decisions into the ledger or ticket a session points at.

An investigation takes each answer as a `decision` entry from the user, in labeled lines, stamped
with the ledger's latest round (1 for an empty ledger). A ticket takes each as a ticket decision
row. Both redact on write. A decision whose redacted text is over the limit is skipped alone and
said on standard error, and the dialog's other decisions are still recorded.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, TextIO

from mightymodels_core.investigations import AddRequest, IncomingEntry
from mightymodels_core.primitives import RedactedTextTooLongError, redaction_within
from mightymodels_core.ticket_decisions import (
    DECISION_TEXT_LIMIT,
    IncomingDecision,
    SqliteTicketDecisionRepository,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mightymodels_core.database import Unit
    from mightymodels_core.investigations import InvestigationService
    from mightymodels_core.primitives import Clock, Slug


@dataclass(slots=True, kw_only=True, frozen=True)
class Answered:
    question: str
    answer: str
    response: str | None = None
    note: str | None = None


def ledger_text(answered: Answered) -> str:
    lines = [answered.question, f'Answer: {answered.answer}']
    if answered.response is not None:
        lines.append(f'Response: {answered.response}')

    if answered.note is not None:
        lines.append(f'Note: {answered.note}')

    return '\n'.join(lines)


def ledger_entry_of(answered: Answered) -> IncomingEntry | RedactedTextTooLongError:
    text = ledger_text(answered)
    try:
        redaction_within(text, 'decision', DECISION_TEXT_LIMIT)
    except RedactedTextTooLongError as error:
        return error

    return IncomingEntry(kind='decision', text=text, source='user')


def decision_of(answered: Answered) -> IncomingDecision:
    return IncomingDecision(
        question=answered.question,
        answer=answered.answer,
        response=answered.response,
        note=answered.note,
    )


@dataclass(slots=True, kw_only=True, frozen=True)
class DecisionRecorder:
    stderr: TextIO
    clock: Clock
    answers: Sequence[Answered]

    def skipped(self, error: RedactedTextTooLongError) -> None:
        self.stderr.write(f'mightymodels-hooks: ask-recorder: skipped a decision: {error}\n')

    def record_ticket(self, unit: Unit, ticket_id: int) -> None:
        decisions = SqliteTicketDecisionRepository(unit=unit, clock=self.clock)
        for answered in self.answers:
            try:
                decisions.add(ticket_id, decision_of(answered))
            except RedactedTextTooLongError as error:
                self.skipped(error)

    def fitting_entries(self) -> list[IncomingEntry]:
        candidates = [ledger_entry_of(answered) for answered in self.answers]
        for candidate in candidates:
            if isinstance(candidate, RedactedTextTooLongError):
                self.skipped(candidate)

        return [entry for entry in candidates if isinstance(entry, IncomingEntry)]

    def record_ledger(self, service: InvestigationService, key: Slug, head: str | None) -> None:
        entries = self.fitting_entries()
        if not entries:
            return

        latest = service.render(key).latest_round
        service.add(key, AddRequest(round=max(latest, 1), entries=entries, head=head))
