"""The decision a dialog records, redacted the way the investigation ledger redacts prose."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mightymodels_core.primitives import redact_within

if TYPE_CHECKING:
    from datetime import datetime

DECISION_TEXT_LIMIT = 4000


def redacted_optional(text: str | None, field: str) -> str | None:
    return None if text is None else redact_within(text, field, DECISION_TEXT_LIMIT)


@dataclass(slots=True, kw_only=True, frozen=True)
class IncomingDecision:
    question: str
    answer: str
    response: str | None = None
    note: str | None = None

    def redacted(self) -> IncomingDecision:
        return IncomingDecision(
            question=redact_within(self.question, 'question', DECISION_TEXT_LIMIT),
            answer=redact_within(self.answer, 'answer', DECISION_TEXT_LIMIT),
            response=redacted_optional(self.response, 'response'),
            note=redacted_optional(self.note, 'note'),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class TicketDecision:
    question: str
    answer: str
    response: str | None
    note: str | None
    decided_at: datetime
