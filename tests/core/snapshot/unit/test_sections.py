"""The pure mapping from ticket decisions to snapshot ledger lines."""

from datetime import UTC, datetime

from mightymodels_core.snapshot import LedgerLine
from mightymodels_core.snapshot.sections import decision_lines
from mightymodels_core.ticket_decisions import TicketDecision

NOW = datetime(2026, 10, 26, tzinfo=UTC)


def create_decision(question: str, answer: str, response: str | None = None) -> TicketDecision:
    return TicketDecision(
        question=question, answer=answer, response=response, note='hidden', decided_at=NOW
    )


class TestDecisionLines:
    def test_a_decision_becomes_a_ticket_ledger_line(self) -> None:
        lines = decision_lines((), [create_decision('Which store?', 'sqlite')], 5)

        assert lines == (
            LedgerLine(kind='decision', text='Which store?: sqlite', cite=None, origin='ticket'),
        )

    def test_the_response_is_appended_and_the_note_is_not_shown(self) -> None:
        (line,) = decision_lines((), [create_decision('Which store?', 'other', 'wal mode')], 5)

        assert line.text == 'Which store?: other - wal mode'

    def test_the_list_is_cut_to_the_last_lines(self) -> None:
        decisions = [create_decision(f'Q{number}?', 'yes') for number in range(3)]

        lines = decision_lines((), decisions, 2)

        assert [line.text for line in lines] == ['Q1?: yes', 'Q2?: yes']

    def test_a_zero_limit_keeps_nothing(self) -> None:
        assert decision_lines((), [create_decision('Q?', 'yes')], 0) == ()
