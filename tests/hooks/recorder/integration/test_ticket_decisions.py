from typing import TYPE_CHECKING

from tests.hooks.recorder.recorder_builders import (
    FIRST,
    SECOND,
    SECRET,
    ask_payload,
    two_answers,
)

if TYPE_CHECKING:
    from tests.hooks.recorder.recorder_builders import RecorderHarness


class TestTicketDecisions:
    async def test_two_questions_yield_two_rows(self, harness: RecorderHarness) -> None:
        ticket_id = await harness.stage_ticket()
        output = await harness.record(ask_payload(two_answers()))
        decisions = await harness.ticket_decisions(ticket_id)
        assert output is None
        assert [(item.question, item.answer) for item in decisions] == [
            (FIRST, 'Redis'),
            (SECOND, 'Lint, Tests'),
        ]
        assert harness.stderr.getvalue() == ''

    async def test_the_response_and_note_are_stored_and_a_secret_is_redacted(
        self, harness: RecorderHarness
    ) -> None:
        ticket_id = await harness.stage_ticket()
        payload = ask_payload(
            {FIRST: f'Other: {SECRET}'}, {FIRST: {'notes': 'a note'}}, response='a response'
        )
        await harness.record(payload)
        (decision,) = await harness.ticket_decisions(ticket_id)
        assert SECRET not in decision.answer
        assert (decision.response, decision.note) == ('a response', 'a note')

    async def test_an_oversized_decision_is_skipped_alone(self, harness: RecorderHarness) -> None:
        ticket_id = await harness.stage_ticket()
        await harness.record(ask_payload({FIRST: 'x' * 4001, SECOND: 'Redis'}))
        (decision,) = await harness.ticket_decisions(ticket_id)
        assert decision.question == SECOND
        assert 'skipped a decision' in harness.stderr.getvalue()
